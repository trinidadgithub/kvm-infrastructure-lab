"""Disposable-root invariants and stub-only controller bootstrap tests."""

import copy
import hashlib
import json
import os
import pty
import re
import runpy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROOT_DIR = ROOT / "environments" / "pty-regression"
VM = "pty-regression-01"
PROVIDER = "registry.terraform.io/dmacvicar/libvirt"


class PtyRegressionConfigTests(unittest.TestCase):
    def test_disposable_module_flags(self):
        text = (ROOT_DIR / "main.tf").read_text(encoding="utf-8")
        self.assertRegex(text, r"enable_guest_agent\s*=\s*true")
        self.assertRegex(text, r"enable_serial_console\s*=\s*false")
        self.assertRegex(text, r"cloudinit_in_pool\s*=\s*true")

    def test_fixed_disposable_identifiers(self):
        text = (ROOT_DIR / "variables.tf").read_text(encoding="utf-8")
        expected = {
            "pool_name": "pty-regression",
            "pool_path": "/var/lib/libvirt/images/labs/pty-regression",
            "network_name": "pty-regression-net",
            "bridge_name": "virbr3",
            "network_cidr": "192.168.125.0/24",
            "gateway_ip": "192.168.125.1",
            "dhcp_start": "192.168.125.100",
            "dhcp_end": "192.168.125.200",
            "base_image": "/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2",
        }
        for name, value in expected.items():
            self.assertRegex(
                text,
                rf'variable "{re.escape(name)}"[\s\S]*?default\s*=\s*"{re.escape(value)}"',
                msg=f"{name} default changed",
            )
        self.assertIn('"pty-regression-01"', text)
        self.assertIn('"52:54:00:cc:00:01"', text)
        self.assertIn('"192.168.125.10"', text)

    def test_controller_has_only_disposable_lifecycle_mapping(self):
        controller = runpy.run_path(str(ROOT / "bin" / "operate"), run_name="test_controller")
        self.assertEqual(controller["ALLOWED_OPERATIONS"]["pty-regression"],
                         {"bootstrap", "cleanup", "recover"})
        self.assertEqual(controller["ENVIRONMENTS"]["pty-regression"], ROOT_DIR)

    def test_preflight_script_is_executable(self):
        script = ROOT / "bin" / "pty-regression-preflight"
        self.assertTrue(script.is_file())
        self.assertTrue(os.access(script, os.X_OK))


class PtyRegressionControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kvm-pty-controller-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pty_root = self.root / "environments" / "pty-regression"
        self.pty_root.mkdir(parents=True)
        (self.root / "bin").mkdir()
        (self.root / "tools").mkdir()
        shutil.copy2(ROOT / "bin" / "operate", self.root / "bin" / "operate")
        self.events = self.root / "events.log"

        terraform = self.root / "tools" / "terraform"
        terraform.write_text(f'''#!/usr/bin/python3
import fcntl, hashlib, sys
from pathlib import Path
root = Path({str(self.root)!r})
args = sys.argv[1:]
with (root / "events.log").open("a") as log:
    log.write("terraform " + " ".join(args) + "\\n")
if args[1:3] == ["show", "-json"]:
    descriptor = int(args[3].rsplit("/", 1)[1])
    if not fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & fcntl.F_SEAL_WRITE:
        sys.exit(9)
    data = Path(args[3]).read_bytes()
    with (root / "events.log").open("a") as log:
        log.write("shown-sha " + hashlib.sha256(data).hexdigest() + "\\n")
    if (root / "replace-plan-after-show").exists():
        (root / "environments/pty-regression/pty-regression.tfplan").write_text("substituted")
    if (root / "replace-destroy-plan-after-show").exists():
        (root / "environments/pty-regression/pty-regression-destroy.tfplan").write_text("substituted")
    print((root / "plan.json").read_text())
elif args[1] == "apply":
    descriptor = int(args[2].rsplit("/", 1)[1])
    if not fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & fcntl.F_SEAL_WRITE:
        sys.exit(9)
    data = Path(args[2]).read_bytes()
    with (root / "events.log").open("a") as log:
        log.write("applied-sha " + hashlib.sha256(data).hexdigest() + "\\n")
    if (root / "fail-partial-apply").exists():
        (root / "environments/pty-regression/terraform.tfstate").write_text("partial fixture state")
        (root / "state-addresses.txt").write_text((root / "partial-addresses.txt").read_text())
        sys.exit(42)
elif args[1:3] == ["state", "list"]:
    print((root / "state-addresses.txt").read_text(), end="")
else:
    sys.exit(7)
''')
        terraform.chmod(0o755)
        virsh = self.root / "tools" / "virsh"
        virsh.write_text(f'''#!/usr/bin/python3
import sys
from pathlib import Path
root = Path({str(self.root)!r})
args = sys.argv[1:]
with (root / "events.log").open("a") as log:
    log.write("virsh " + " ".join(args) + "\\n")
if args[:2] != ["-c", "qemu:///system"]:
    sys.exit(7)
command = args[2:]
if command == ["domuuid", "pty-regression-01"]:
    if (root / "no-domain").exists():
        sys.exit(1)
    print("wrong-uuid" if (root / "wrong-uuid").exists() else "fixture-uuid")
elif command == ["list", "--all", "--name"]:
    if (root / "replace-plan-after-recheck").exists():
        if (root / "first-list-done").exists():
            (root / "environments/pty-regression/pty-regression.tfplan").write_text("substituted after rehash")
        else:
            (root / "first-list-done").touch()
    if (root / "orphan-domain").exists():
        print("ubuntu-server-01\\nubuntu-server-02\\npty-regression-01")
        sys.exit(0)
    if (root / "conflict-domain").exists():
        print("pty-regression-01")
    elif ((root / "environments/pty-regression/terraform.tfstate").exists() and
          not (root / "no-domain").exists() and
          "libvirt_domain.vm" in (root / "state-addresses.txt").read_text()):
        print("ubuntu-server-01\\nubuntu-server-02\\npty-regression-01")
    else:
        print("ubuntu-server-01\\nubuntu-server-02")
elif command == ["net-list", "--all", "--name"]:
    print("pty-regression-net" if (root / "conflict-network").exists() else "default\\nubuntu-servers-net")
elif command == ["pool-list", "--all", "--name"]:
    print("pty-regression" if (root / "conflict-pool").exists() else "clone-test\\nubuntu-servers")
elif command[:1] == ["dumpxml"]:
    mac = "52:54:00:cc:00:01" if (root / "conflict-mac").exists() else "52:54:00:bb:00:01"
    source = "<source network='pty-regression-net'/>" if (root / "other-domain-uses-network").exists() else ""
    disk = "<disk><source file='/var/lib/libvirt/images/labs/pty-regression/other.qcow2'/></disk>" if (root / "other-domain-uses-disk").exists() else ""
    print("<domain><devices><interface><mac address='" + mac + "'/>" + source + "</interface>" + disk + "</devices></domain>")
elif command[:1] == ["net-dumpxml"]:
    if command[1] == "pty-regression-net":
        uuid = "wrong-network-uuid" if (root / "wrong-network-uuid").exists() else "fixture-network-uuid"
        print("<network><uuid>" + uuid + "</uuid><bridge name='virbr3'/><ip address='192.168.125.1' netmask='255.255.255.0'/></network>")
    else:
        bridge = "virbr3" if (root / "conflict-bridge").exists() else "virbr2"
        ip = "192.168.125.1" if (root / "conflict-subnet").exists() else "192.168.124.1"
        print("<network><bridge name='" + bridge + "'/><ip address='" + ip + "' netmask='255.255.255.0'/></network>")
elif command[:1] == ["pool-dumpxml"]:
    if command[1] == "pty-regression":
        uuid = "wrong-pool-uuid" if (root / "wrong-pool-uuid").exists() else "fixture-pool-uuid"
        print("<pool><uuid>" + uuid + "</uuid><target><path>/var/lib/libvirt/images/labs/pty-regression</path></target></pool>")
    else:
        path = "/var/lib/libvirt/images/labs/pty-regression" if (root / "conflict-pool-path").exists() else "/var/lib/libvirt/images/labs/ubuntu-servers"
        print("<pool><target><path>" + path + "</path></target></pool>")
elif command == ["vol-list", "--pool", "pty-regression"]:
    state = (root / "state-addresses.txt").read_text()
    print(" Name Path\\n----------------------")
    if "libvirt_volume.vm_disk" in state: print(" pty-regression-01.qcow2 /tmp/pty-regression-01.qcow2")
    if "libvirt_volume.cloudinit_iso" in state: print(" pty-regression-01-cloudinit.iso /tmp/pty-regression-01-cloudinit.iso")
    if (root / "extra-volume").exists(): print(" ubuntu-server-01.qcow2 /tmp/ubuntu-server-01.qcow2")
else:
    sys.exit(7)
''')
        virsh.chmod(0o755)
        manifest = {
            "executables": {
                "terraform": {"path": str(terraform), "resolved": str(terraform.resolve())},
                "virsh": {"path": str(virsh), "resolved": str(virsh.resolve())},
            }
        }
        (self.root / ".local-tools.json").write_text(json.dumps(manifest))
        self.plan = self.valid_plan()
        (self.root / "state-addresses.txt").write_text(
            "\n".join(item["address"] for item in self.plan["resource_changes"]) + "\n")
        self.save_plan("bootstrap")

    @staticmethod
    def valid_plan():
        values = {
            "libvirt_pool.pty_regression": {
                "name": "pty-regression", "type": "dir", "uuid": "fixture-pool-uuid",
                "target": {"path": "/var/lib/libvirt/images/labs/pty-regression"},
            },
            "libvirt_network.pty_regression": {
                "name": "pty-regression-net", "uuid": "fixture-network-uuid",
                "bridge": {"name": "virbr3"},
                "forward": {"mode": "nat"},
                "ips": [{"address": "192.168.125.1", "netmask": "255.255.255.0",
                         "dhcp": {"hosts": [{"name": VM, "mac": "52:54:00:cc:00:01",
                                              "ip": "192.168.125.10"}],
                                  "ranges": [{"start": "192.168.125.100",
                                              "end": "192.168.125.200"}]}}],
            },
            f'module.compute.libvirt_volume.vm_disk["{VM}"]': {
                "name": f"{VM}.qcow2", "pool": "pty-regression", "capacity": 20 * 1024**3,
                "backing_store": {"path": "/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2",
                                  "format": {"type": "qcow2"}},
            },
            f'module.compute.libvirt_cloudinit_disk.commoninit["{VM}"]': {
                "name": f"{VM}-cloudinit", "meta_data": f"instance-id: iid-{VM}\\n",
            },
            f'module.compute.libvirt_volume.cloudinit_iso["{VM}"]': {
                "name": f"{VM}-cloudinit.iso", "pool": "pty-regression",
            },
            f'module.compute.libvirt_domain.vm["{VM}"]': {
                "name": VM, "type": "kvm", "running": True, "memory": 2048,
                "memory_unit": "MiB", "vcpu": 2, "uuid": "fixture-uuid",
                "devices": {"consoles": [],
                            "channels": [{"target": {"virt_io": {"name": "org.qemu.guest_agent.0"}}}],
                            "interfaces": [{"mac": {"address": "52:54:00:cc:00:01"},
                                            "source": {"network": {"network": "pty-regression-net"}}}]},
            },
        }
        return {
            "configuration": {"provider_config": {"libvirt": {
                "full_name": PROVIDER, "version_constraint": "0.9.9",
                "expressions": {"uri": {"references": ["var.libvirt_uri"]}},
            }}},
            "prior_state": {"values": {"root_module": {}}},
            "variables": {
                "libvirt_uri": {"value": "qemu:///system"},
                "base_image": {"value": "/var/lib/libvirt/images/labs/base/ubuntu-24.04-v1.qcow2"},
                "base_image_sha256": {"value": "4d6565fd43a775899b03730e72daca4669f8c71ce57e31482b5520965aef790d"},
                "pool_group_id": {"value": "64055"},
            },
            "resource_changes": [
                {"address": address, "mode": "managed", "provider_name": PROVIDER,
                 "change": {"actions": ["create"], "before": None, "after": value}}
                for address, value in values.items()
            ],
        }

    def save_plan(self, operation):
        filename = {"bootstrap": "pty-regression.tfplan",
                    "cleanup": "pty-regression-destroy.tfplan",
                    "recover": "pty-regression-recovery.tfplan"}[operation]
        if operation != "bootstrap":
            self.plan["prior_state"]["values"]["root_module"] = {
                "resources": [{"address": item["address"]} for item in self.plan["resource_changes"]]
            }
        (self.pty_root / filename).write_text("stub saved plan")
        (self.root / "plan.json").write_text(json.dumps(self.plan))

    def token(self, operation):
        filename = {"bootstrap": "pty-regression.tfplan",
                    "cleanup": "pty-regression-destroy.tfplan",
                    "recover": "pty-regression-recovery.tfplan"}[operation]
        digest = hashlib.sha256((self.pty_root / filename).read_bytes()).hexdigest()
        return f"{operation} pty-regression {digest}"

    def destroy_plan(self, operation, partial=False):
        self.plan = copy.deepcopy(self.valid_plan())
        if partial:
            self.plan["resource_changes"] = [item for item in self.plan["resource_changes"]
                                             if 'libvirt_domain.vm' not in item["address"]]
        for resource in self.plan["resource_changes"]:
            change = resource["change"]
            change["actions"] = ["delete"]
            change["before"], change["after"] = change["after"], None
        self.save_plan(operation)

    def call(self, operation, answer=None, environment="pty-regression"):
        command = ["/usr/bin/python3", "-I", str(self.root / "bin" / "operate"),
                   operation, environment]
        if answer is None:
            return subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=10)
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(command, cwd=self.root, stdin=slave,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            os.close(slave)
            slave = -1
            os.write(master, answer.encode() + b"\n")
            stdout, stderr = process.communicate(timeout=10)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            os.close(master)
            if slave != -1:
                os.close(slave)

    def applied(self):
        return [line for line in self.events.read_text().splitlines()
                if " apply " in line] if self.events.exists() else []

    def test_bootstrap_requires_exact_token_absent_state_and_fixed_plan(self):
        manifest = self.root / ".local-tools.json"
        manifest_contents = manifest.read_text()
        manifest.unlink()
        self.assertNotEqual(self.call("bootstrap", self.token("bootstrap")).returncode, 0)
        self.assertEqual(self.applied(), [])
        manifest.write_text(manifest_contents)
        plan = self.pty_root / "pty-regression.tfplan"
        plan.unlink()
        self.assertNotEqual(self.call("bootstrap", "bootstrap pty-regression").returncode, 0)
        self.assertEqual(self.applied(), [])
        plan.symlink_to(self.root / "plan.json")
        self.assertNotEqual(self.call("bootstrap", "bootstrap pty-regression").returncode, 0)
        self.assertEqual(self.applied(), [])
        plan.unlink()
        self.save_plan("bootstrap")
        self.assertNotEqual(self.call("bootstrap").returncode, 0)  # no TTY
        self.assertNotEqual(self.call("bootstrap", "yes").returncode, 0)
        self.assertEqual(self.applied(), [])
        approved = self.call("bootstrap", self.token("bootstrap"))
        self.assertEqual(approved.returncode, 0, (approved.stdout, approved.stderr))
        self.assertEqual(len(self.applied()), 1)
        self.events.unlink()
        (self.pty_root / "terraform.tfstate").write_text("fixture state")
        self.assertNotEqual(self.call("bootstrap", self.token("bootstrap")).returncode, 0)
        self.assertEqual(self.applied(), [])

    def test_bootstrap_rejects_out_of_scope_or_changed_plan(self):
        for mutation in (
            lambda p: p["resource_changes"][0].update(address="libvirt_pool.ubuntu_servers"),
            lambda p: p["resource_changes"][0]["change"].update(actions=["update"]),
            lambda p: p["resource_changes"][0]["change"].update(actions=["delete"]),
            lambda p: p["resource_changes"][0]["change"].update(actions=["delete", "create"]),
            lambda p: p["resource_changes"].append(copy.deepcopy(p["resource_changes"][0])),
            lambda p: p["resource_changes"][5]["change"]["after"]["devices"].update(consoles=[{}]),
            lambda p: p["resource_changes"][2]["change"]["after"]["backing_store"].update(path="/wrong-image"),
            lambda p: p["variables"]["libvirt_uri"].update(value="qemu:///session"),
            lambda p: p["configuration"]["provider_config"]["libvirt"]["expressions"].update(
                uri={"constant_value": "qemu:///session"}),
            lambda p: p["prior_state"]["values"]["root_module"].update(
                resources=[{"address": "libvirt_pool.ubuntu_servers"}]),
            lambda p: p.update(resource_drift=[{"address": "libvirt_pool.ubuntu_servers"}]),
        ):
            with self.subTest(mutation=mutation):
                self.plan = self.valid_plan()
                mutation(self.plan)
                self.save_plan("bootstrap")
                self.events.unlink(missing_ok=True)
                result = self.call("bootstrap", self.token("bootstrap"))
                self.assertNotEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertEqual(self.applied(), [])

    def test_bootstrap_refuses_state_artifacts_and_libvirt_collisions(self):
        for name in ("terraform.tfstate.backup", "terraform.tfstate.lock.info", "terraform.tfstate.d",
                     ".terraform/terraform.tfstate"):
            with self.subTest(state_artifact=name):
                path = self.pty_root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                self.events.unlink(missing_ok=True)
                self.assertNotEqual(self.call("bootstrap", self.token("bootstrap")).returncode, 0)
                self.assertEqual(self.applied(), [])
                path.unlink()
        for flag in ("conflict-domain", "conflict-network", "conflict-pool", "conflict-mac",
                     "conflict-bridge", "conflict-subnet", "conflict-pool-path"):
            with self.subTest(libvirt_collision=flag):
                marker = self.root / flag
                marker.touch()
                self.events.unlink(missing_ok=True)
                self.assertNotEqual(self.call("bootstrap", self.token("bootstrap")).returncode, 0)
                self.assertEqual(self.applied(), [])
                marker.unlink()

    def test_sealed_plan_bytes_survive_path_replacement_after_final_rehash(self):
        original = hashlib.sha256((self.pty_root / "pty-regression.tfplan").read_bytes()).hexdigest()
        (self.root / "replace-plan-after-recheck").touch()
        result = self.call("bootstrap", self.token("bootstrap"))
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        events = self.events.read_text().splitlines()
        self.assertIn("shown-sha " + original, events)
        self.assertIn("applied-sha " + original, events)
        self.assertNotEqual(hashlib.sha256((self.pty_root / "pty-regression.tfplan").read_bytes()).hexdigest(),
                            original)

    def test_plan_substitution_during_inspection_fails_closed(self):
        (self.root / "replace-plan-after-show").touch()
        result = self.call("bootstrap", self.token("bootstrap"))
        self.assertNotEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(self.applied(), [])

    def test_cleanup_requires_state_destroy_only_plan_and_uuid_match(self):
        self.destroy_plan("cleanup")
        self.assertNotEqual(self.call("cleanup", self.token("cleanup")).returncode, 0)
        self.assertEqual(self.applied(), [])
        (self.pty_root / "terraform.tfstate").write_text("fixture state")
        (self.pty_root / "pty-regression-destroy.tfplan").unlink()
        self.assertNotEqual(self.call("cleanup", "cleanup pty-regression").returncode, 0)
        self.save_plan("cleanup")
        self.plan["resource_changes"][0]["change"]["actions"] = ["create"]
        self.save_plan("cleanup")
        self.assertNotEqual(self.call("cleanup", self.token("cleanup")).returncode, 0)
        self.assertEqual(self.applied(), [])
        self.plan["resource_changes"][0]["change"]["actions"] = ["delete"]
        self.save_plan("cleanup")
        (self.root / "wrong-uuid").touch()
        self.assertNotEqual(self.call("cleanup", self.token("cleanup")).returncode, 0)
        self.assertEqual(self.applied(), [])
        (self.root / "wrong-uuid").unlink()
        self.assertNotEqual(self.call("cleanup", "no").returncode, 0)
        self.assertEqual(self.applied(), [])
        approved = self.call("cleanup", self.token("cleanup"))
        self.assertEqual(approved.returncode, 0, (approved.stdout, approved.stderr))
        self.assertEqual(len(self.applied()), 1)

    def test_cleanup_plan_substitution_and_wrong_digest_are_refused(self):
        (self.pty_root / "terraform.tfstate").write_text("fixture state")
        self.destroy_plan("cleanup")
        self.assertNotEqual(self.call("cleanup", "cleanup pty-regression " + "0" * 64).returncode, 0)
        self.assertEqual(self.applied(), [])
        (self.root / "replace-destroy-plan-after-show").touch()
        self.assertNotEqual(self.call("cleanup", self.token("cleanup")).returncode, 0)
        self.assertEqual(self.applied(), [])

    def test_failed_domain_creation_uses_separate_partial_recovery(self):
        partial = [item["address"] for item in self.plan["resource_changes"]
                   if 'libvirt_domain.vm' not in item["address"]]
        (self.root / "partial-addresses.txt").write_text("\n".join(partial) + "\n")
        (self.root / "fail-partial-apply").touch()
        failed = self.call("bootstrap", self.token("bootstrap"))
        self.assertEqual(failed.returncode, 42, (failed.stdout, failed.stderr))
        self.assertTrue((self.pty_root / "terraform.tfstate").is_file())
        (self.root / "fail-partial-apply").unlink()
        (self.root / "no-domain").touch()
        self.events.unlink()
        self.assertNotEqual(self.call("bootstrap", self.token("bootstrap")).returncode, 0)
        self.assertEqual(self.applied(), [])
        self.destroy_plan("cleanup")
        self.assertNotEqual(self.call("cleanup", self.token("cleanup")).returncode, 0)
        self.assertEqual(self.applied(), [])
        self.destroy_plan("recover", partial=True)
        refused = self.call("recover", "recover pty-regression")
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.applied(), [])
        approved = self.call("recover", self.token("recover"))
        self.assertEqual(approved.returncode, 0, (approved.stdout, approved.stderr))
        self.assertEqual(len(self.applied()), 1)

    def test_partial_recovery_refuses_orphan_or_unowned_state(self):
        (self.pty_root / "terraform.tfstate").write_text("fixture partial state")
        (self.root / "no-domain").touch()
        self.destroy_plan("recover", partial=True)
        addresses = [item["address"] for item in self.plan["resource_changes"]]
        state_file = self.root / "state-addresses.txt"
        state_file.write_text("\n".join(addresses + ["libvirt_pool.ubuntu_servers"]) + "\n")
        self.assertNotEqual(self.call("recover", self.token("recover")).returncode, 0)
        self.assertEqual(self.applied(), [])
        state_file.write_text("\n".join(addresses) + "\n")
        (self.root / "orphan-domain").touch()
        self.assertNotEqual(self.call("recover", self.token("recover")).returncode, 0)
        self.assertEqual(self.applied(), [])
        (self.root / "orphan-domain").unlink()
        self.destroy_plan("recover", partial=False)
        self.assertNotEqual(self.call("recover", self.token("recover")).returncode, 0)
        self.assertEqual(self.applied(), [])

    def test_cleanup_and_recovery_refuse_replaced_objects_or_extra_volumes(self):
        (self.pty_root / "terraform.tfstate").write_text("fixture state")
        for operation, partial in (("cleanup", False), ("recover", True)):
            with self.subTest(operation=operation):
                self.destroy_plan(operation, partial=partial)
                addresses = [item["address"] for item in self.plan["resource_changes"]]
                (self.root / "state-addresses.txt").write_text("\n".join(addresses) + "\n")
                for flag in ("wrong-pool-uuid", "wrong-network-uuid", "extra-volume",
                             "other-domain-uses-network", "other-domain-uses-disk"):
                    with self.subTest(operation=operation, conflict=flag):
                        marker = self.root / flag
                        marker.touch()
                        self.events.unlink(missing_ok=True)
                        self.assertNotEqual(self.call(operation, self.token(operation)).returncode, 0)
                        self.assertEqual(self.applied(), [])
                        marker.unlink()

    def test_destroy_plans_cannot_name_persistent_resources(self):
        (self.pty_root / "terraform.tfstate").write_text("fixture state")
        for operation, partial in (("cleanup", False), ("recover", True)):
            with self.subTest(operation=operation):
                self.destroy_plan(operation, partial=partial)
                addresses = [item["address"] for item in self.plan["resource_changes"]]
                (self.root / "state-addresses.txt").write_text("\n".join(addresses) + "\n")
                for address, replacement in (("libvirt_pool.pty_regression", "ubuntu-servers"),
                                             ("libvirt_network.pty_regression", "lab-net")):
                    with self.subTest(operation=operation, address=address):
                        item = next(item for item in self.plan["resource_changes"] if item["address"] == address)
                        original = item["change"]["before"]["name"]
                        item["change"]["before"]["name"] = replacement
                        self.save_plan(operation)
                        self.events.unlink(missing_ok=True)
                        self.assertNotEqual(self.call(operation, self.token(operation)).returncode, 0)
                        self.assertEqual(self.applied(), [])
                        item["change"]["before"]["name"] = original

    def test_other_operations_and_cross_root_bootstrap_are_refused(self):
        for operation in ("apply", "destroy", "configure", "snapshot", "build", "up"):
            with self.subTest(operation=operation):
                self.assertNotEqual(self.call(operation, "yes").returncode, 0)
        for operation in ("bootstrap", "cleanup", "recover"):
            for environment in ("k3s-lab", "ubuntu-servers"):
                with self.subTest(operation=operation, environment=environment):
                    self.assertNotEqual(self.call(operation, "yes", environment).returncode, 0)
        self.assertEqual(self.applied(), [])


if __name__ == "__main__":
    unittest.main()
