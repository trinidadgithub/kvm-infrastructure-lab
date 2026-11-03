"""Isolated controller/Make tests. All external operations are absolute-path stubs."""

import concurrent.futures
import fcntl
import json
import os
import pty
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class MakeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kvm-make-safety-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ("bin", "tools", "terraform", "environments/ubuntu-servers", "ansible", "packer"):
            (self.root / relative).mkdir(parents=True)
        shutil.copyfile(REPO / "Makefile", self.root / "Makefile")
        shutil.copy2(REPO / "bin/operate", self.root / "bin/operate")
        (self.root / "terraform/terraform.tfstate").write_text("fixture only\n")
        (self.root / "environments/ubuntu-servers/terraform.tfstate").write_text("fixture only\n")
        (self.root / "k3s.pub").write_text("fixture public key\n")
        (self.root / "build.key").write_text("fixture build key\n")
        (self.root / "k3s-tmp").mkdir()
        self.log = self.root / "events.log"
        self.env = dict(os.environ, PKR_VAR_ssh_private_key=str(self.root / "build.key"))
        self.env["PATH"] = f"{self.root / 'tools'}:{os.environ['PATH']}"

        common = f'''#!/usr/bin/python3
import json, os, sys, time
from pathlib import Path
root = Path({str(self.root)!r})
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "events.log").open("a") as log:
    log.write(name + " " + " ".join(args) + "\\n")
if name == "terraform":
    if args[-3:] == ["output", "-json", "vm_names"]:
        print(json.dumps(["jumpbox", "k3s-master"] if args[0] == "-chdir=" + str(root / "terraform") else ["ubuntu-server-01", "ubuntu-server-02"]))
    elif args[-3:] == ["output", "-json", "vm_uuids"]:
        print(json.dumps({{"jumpbox": "k3s-uuid", "k3s-master": "master-uuid"}} if args[0] == "-chdir=" + str(root / "terraform") else {{"ubuntu-server-01": "ubuntu-uuid-01", "ubuntu-server-02": "ubuntu-uuid-02"}}))
    elif args[-1] == "apply" and (root / "slow-apply").exists():
        with (root / "timing.log").open("a") as log: log.write("START " + str(time.time_ns()) + "\\n")
        time.sleep(0.7)
        with (root / "timing.log").open("a") as log: log.write("END " + str(time.time_ns()) + "\\n")
    if args[-1] == "apply" and (root / "fail-terraform-42").exists(): sys.exit(42)
    for key in ("TF_CLI_ARGS", "TF_CLI_ARGS_apply", "TF_WORKSPACE", "TF_VAR_libvirt_uri"):
        if key in os.environ:
            with (root / "leaked-env").open("a") as log: log.write(key + "\\n")
if name == "virsh":
    if args[:3] == ["-c", "qemu:///system", "domuuid"]:
        print("wrong-uuid" if (root / "mismatch").exists() else {{"jumpbox": "k3s-uuid", "k3s-master": "master-uuid", "ubuntu-server-01": "ubuntu-uuid-01", "ubuntu-server-02": "ubuntu-uuid-02"}}.get(args[3], "unknown"))
    if "pool-info" in args and (root / "fail-pool").exists(): sys.exit(1)
if name == "ansible-playbook" and (root / "fail-ansible").exists(): sys.exit(1)
'''
        entries = {}
        for tool in ("terraform", "virsh", "ansible-playbook", "packer"):
            path = self.root / "tools" / tool
            path.write_text(common)
            path.chmod(0o755)
            entries[{"ansible-playbook": "ansible_playbook"}.get(tool, tool)] = {
                "path": str(path), "resolved": str(path.resolve())
            }
        self.config = {"executables": entries, "k3s_tmpdir": str(self.root / "k3s-tmp"),
                       "k3s_ssh_public_key": str(self.root / "k3s.pub")}
        self.save_config()
        seed = self.root / "packer/create-seed.sh"
        seed.write_text(f'#!/bin/bash\n/usr/bin/python3 -c "open({str(self.log)!r}, \'a\').write(\'seed\\\\n\')"\n')

    def save_config(self):
        (self.root / ".local-tools.json").write_text(json.dumps(self.config))

    def events(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def reset_events(self):
        self.log.unlink(missing_ok=True)

    def call(self, args, answer=None, *, eof=False, interrupt=False, env=None, direct=None):
        env = env or self.env
        command = (["/usr/bin/python3", "-I", str(self.root / "bin/operate"), *direct]
                   if direct is not None else ["/usr/bin/make", "--no-print-directory", *args])
        if answer is None and not eof and not interrupt:
            return subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, timeout=10)
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(command, cwd=self.root, env=env, stdin=slave,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True, text=True)
            os.close(slave)
            slave = -1
            if answer is not None:
                os.write(master, answer.encode() + b"\n")
            if eof:
                os.close(master)
                master = -1
            if interrupt:
                time.sleep(0.2)
                os.killpg(process.pid, signal.SIGINT)
            stdout, stderr = process.communicate(timeout=10)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            if master != -1:
                os.close(master)
            if slave != -1:
                os.close(slave)

    def protected_events(self):
        return [event for event in self.events() if
                event.startswith("terraform ") and (event.endswith(" apply") or event.endswith(" destroy")) or
                event.startswith("virsh ") and "snapshot-create-as" in event or
                event.startswith("ansible-playbook ") or event.startswith("packer build")]

    def test_denials_and_interrupts(self):
        for args, token in [
            (["ENV=k3s-lab", "tf-destroy"], "destroy k3s-lab"),
            (["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers"),
            (["ENV=ubuntu-servers", "env-ansible-site"], "configure ubuntu-servers"),
            (["ENV=ubuntu-servers", "VM=ubuntu-server-01", "snapshot"], "snapshot ubuntu-servers ubuntu-server-01"),
            (["packer-build"], "build ubuntu-servers"),
        ]:
            for answer, flags in (("no", {}), ("", {}), ("YES", {}), ("destroy wrong-env", {}),
                                  (None, {"eof": True}), (None, {"interrupt": True}), (None, {})):
                with self.subTest(args=args, answer=answer, flags=flags):
                    self.reset_events()
                    result = self.call(args, answer, **flags)
                    self.assertNotEqual(result.returncode, 0, (result.stdout, result.stderr))
                    self.assertEqual(self.protected_events(), [])

    def test_exact_positive_targets(self):
        cases = [
            (["ENV=k3s-lab", "tf-destroy"], "destroy k3s-lab", "terraform -chdir=" + str(self.root / "terraform") + " destroy"),
            (["ENV=ubuntu-servers", "env-tf-destroy"], "destroy ubuntu-servers", "terraform -chdir=" + str(self.root / "environments/ubuntu-servers") + " destroy"),
            (["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers", "terraform -chdir=" + str(self.root / "environments/ubuntu-servers") + " apply"),
            (["ENV=ubuntu-servers", "env-ansible-site"], "configure ubuntu-servers", "ansible-playbook -i inventories/ubuntu-servers.py playbooks/ubuntu-servers.yaml"),
            (["ENV=ubuntu-servers", "VM=ubuntu-server-01", "snapshot"], "snapshot ubuntu-servers ubuntu-server-01", "virsh -c qemu:///system snapshot-create-as ubuntu-server-01"),
            (["packer-build"], "build ubuntu-servers", "packer build ."),
        ]
        for args, token, expected in cases:
            with self.subTest(args=args):
                self.reset_events()
                result = self.call(args, token)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertEqual(len(self.protected_events()), 1, self.events())
                self.assertTrue(self.protected_events()[0].startswith(expected), self.events())
                self.assertIn(f'Type exactly "{token}"', result.stderr)
                self.assertIn("Executing:", result.stdout)
                self.assertIn("exited 0", result.stdout)

    def test_make_and_directory_overrides_cannot_redirect(self):
        attempts = [
            (["ENV=k3s-lab", "MAKE=sh -c 'terraform destroy -auto-approve' #", "tf-destroy"], None),
            (["ENV=ubuntu-servers", "ANSIBLE_DIR=ansible; terraform destroy -auto-approve; true", "env-ansible-site"], "configure ubuntu-servers"),
            (["PACKER_DIR=packer; terraform destroy -auto-approve; true", "packer-build"], "build ubuntu-servers"),
        ]
        for args, token in attempts:
            with self.subTest(args=args):
                self.reset_events()
                result = self.call(args, token)
                if token is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.protected_events(), [])
                else:
                    self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                    self.assertEqual(len(self.protected_events()), 1, self.events())
                    self.assertFalse(any(event.startswith("terraform ") for event in self.protected_events()))

        for inherited in ("MAKE", "MAKEFLAGS"):
            with self.subTest(inherited=inherited):
                self.reset_events()
                env = dict(self.env, **{inherited: "sh -c 'terraform destroy -auto-approve' #" if inherited == "MAKE" else
                                        "MAKE=sh\\ -c\\ 'terraform\\ destroy\\ -auto-approve'\\ #"})
                result = self.call(["ENV=k3s-lab", "tf-apply"], "apply k3s-lab", env=env)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertEqual(self.protected_events(),
                                 ["terraform -chdir=" + str(self.root / "terraform") + " apply"])

        self.reset_events()
        result = self.call(["ENV=k3s-lab", "ENV_TF_DIR=environments/ubuntu-servers",
                            "TF_DIR=environments/ubuntu-servers", "OPERATE_ENV=ubuntu-servers",
                            "env-tf-apply"], "apply k3s-lab")
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(self.protected_events(),
                         ["terraform -chdir=" + str(self.root / "terraform") + " apply"])

    def test_shell_path_and_runtime_environment_overrides(self):
        evil = self.root / "evil-shell"
        evil.write_text("#!/usr/bin/python3\nimport sys\nsys.exit(99)\n")
        evil.chmod(0o755)
        forged = self.root / "evil-path"
        forged.mkdir()
        for name in ("bash", "terraform", "python3"):
            fake = forged / name
            fake.write_text("#!/usr/bin/python3\nimport sys\nsys.exit(99)\n")
            fake.chmod(0o755)
        env = dict(self.env, PATH=f"{forged}:{self.env['PATH']}", SHELL=str(evil),
                   TF_CLI_ARGS="-auto-approve", TF_CLI_ARGS_apply="-auto-approve",
                   TF_WORKSPACE="other", TF_VAR_libvirt_uri="qemu:///session", ANSIBLE_CONFIG="/tmp/evil",
                   ENV_TF_DIR="terraform", OPERATE_ENV="k3s-lab")
        self.reset_events()
        self.assertNotEqual(self.call(["ENV=ubuntu-servers", f"SHELL={evil}", "env-tf-destroy"], env=env).returncode, 0)
        self.assertEqual(self.protected_events(), [])
        self.assertEqual(self.call(["ENV=ubuntu-servers", f"SHELL={evil}", "env-tf-apply"],
                                   "apply ubuntu-servers", env=env).returncode, 0)
        self.assertEqual(len(self.protected_events()), 1)
        self.assertFalse((self.root / "leaked-env").exists())

    def test_symlink_target_change_fails_before_approval(self):
        symlink = self.root / "terraform-link"
        symlink.symlink_to(self.root / "tools/terraform")
        self.config["executables"]["terraform"]["path"] = str(symlink)
        self.save_config()
        accepted = self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers")
        self.assertEqual(accepted.returncode, 0, (accepted.stdout, accepted.stderr))
        self.assertEqual(len(self.protected_events()), 1)
        self.reset_events()
        other = self.root / "tools/terraform-other"
        other.write_text("#!/usr/bin/python3\n")
        other.chmod(0o755)
        symlink.unlink()
        symlink.symlink_to(other)
        result = self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.protected_events(), [])

    def test_missing_manifest_or_state_fails_closed(self):
        (self.root / ".local-tools.json").unlink()
        self.assertNotEqual(self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers").returncode, 0)
        self.assertEqual(self.protected_events(), [])
        (self.root / ".local-tools.json").write_text("{invalid JSON")
        self.assertNotEqual(self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers").returncode, 0)
        self.assertEqual(self.protected_events(), [])
        self.save_config()
        (self.root / "terraform/terraform.tfstate").unlink()
        self.assertNotEqual(self.call(["ENV=k3s-lab", "tf-destroy"], "destroy k3s-lab").returncode, 0)
        self.assertEqual(self.protected_events(), [])
        (self.root / "environments/ubuntu-servers/terraform.tfstate").unlink()
        self.assertNotEqual(self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers").returncode, 0)
        self.assertEqual(self.protected_events(), [])

    def test_manifest_validation_is_read_only(self):
        command = ["/usr/bin/python3", "-I", str(self.root / "bin/operate"),
                   "validate-tools", "ubuntu-servers"]
        result = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertIn(str(self.root / "tools/terraform"), result.stdout)
        self.assertEqual(self.events(), [])
        self.assertFalse((self.root / ".local-operations.lock").exists())
        self.config["executables"]["terraform"]["resolved"] = str(self.root / "wrong-terraform")
        self.save_config()
        result = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events(), [])
        self.assertFalse((self.root / ".local-operations.lock").exists())

    def test_child_status_and_lock_release(self):
        (self.root / "fail-terraform-42").touch()
        failed = self.call([], "apply ubuntu-servers", direct=("apply", "ubuntu-servers"))
        self.assertEqual(failed.returncode, 42, (failed.stdout, failed.stderr))
        self.assertIn("exited 42", failed.stdout)
        via_make = self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers")
        self.assertEqual(via_make.returncode, 2)
        self.assertIn("exited 42", via_make.stdout)
        (self.root / "fail-terraform-42").unlink()
        approved = self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers")
        self.assertEqual(approved.returncode, 0, (approved.stdout, approved.stderr))
        self.assertEqual(len(self.protected_events()), 3)

        self.reset_events()
        with (self.root / ".local-operations.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            busy = self.call(["ENV=ubuntu-servers", "env-tf-destroy"], "destroy ubuntu-servers")
            self.assertNotEqual(busy.returncode, 0)
            self.assertEqual(self.protected_events(), [])
        after = self.call(["ENV=ubuntu-servers", "env-tf-destroy"], "destroy ubuntu-servers")
        self.assertEqual(after.returncode, 0, (after.stdout, after.stderr))
        self.assertEqual(len(self.protected_events()), 1)

    def test_wrong_environment_vm_and_command_arguments_refused(self):
        for args in (["env-tf-destroy"], ["ENV=ubuntu-servers", "tf-destroy"],
                     ["ENV=ubuntu-servers", "VM=jumpbox", "snapshot"],
                     ["ENV=ubuntu-servers", "VM=unknown", "snapshot"],
                     ["ENV=ubuntu-servers", "VM=ubuntu-server-01;terraform destroy", "snapshot"]):
            with self.subTest(args=args):
                self.reset_events()
                self.assertNotEqual(self.call(args, "destroy ubuntu-servers").returncode, 0)
                self.assertEqual(self.protected_events(), [])
        (self.root / "mismatch").touch()
        result = self.call(["ENV=ubuntu-servers", "VM=ubuntu-server-01", "snapshot"],
                           "snapshot ubuntu-servers ubuntu-server-01")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.protected_events(), [])
        command = ["/usr/bin/python3", "-I", str(self.root / "bin/operate"), "apply", "k3s-lab", "--",
                   "terraform", "-chdir=environments/ubuntu-servers", "destroy"]
        result = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.protected_events(), [])

    def test_up_order_refusal_and_partial_failure(self):
        for flags in ([], ["-j4"]):
            with self.subTest(flags=flags):
                self.reset_events()
                result = self.call([*flags, "ENV=k3s-lab", "up"], "apply k3s-lab\nconfigure k3s-lab")
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                events = self.events()
                self.assertLess(events.index("virsh -c qemu:///system pool-info lab"),
                                events.index("terraform -chdir=" + str(self.root / "terraform") + " apply"))
                self.assertLess(events.index("terraform -chdir=" + str(self.root / "terraform") + " apply"),
                                events.index("ansible-playbook -i inventories/terraform.py playbooks/site.yaml"))
        self.reset_events()
        (self.root / "fail-pool").touch()
        self.assertNotEqual(self.call(["-j4", "ENV=k3s-lab", "up"], "apply k3s-lab\nconfigure k3s-lab").returncode, 0)
        self.assertEqual(self.protected_events(), [])
        (self.root / "fail-pool").unlink()
        self.reset_events()
        result = self.call(["ENV=k3s-lab", "up"], "apply k3s-lab\nno")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.protected_events()), 1)
        self.assertTrue(self.protected_events()[0].endswith(" apply"))
        (self.root / "fail-ansible").touch()
        self.reset_events()
        failed = self.call(["ENV=k3s-lab", "up"], "apply k3s-lab\nconfigure k3s-lab")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("exited 1", failed.stdout)
        self.assertEqual(len(self.protected_events()), 2)
        self.assertFalse(any(event.endswith(" destroy") for event in self.events()))

    def test_parallel_processes_cannot_overlap(self):
        (self.root / "slow-apply").touch()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.call(["ENV=ubuntu-servers", "env-tf-apply"], "apply ubuntu-servers"), range(2)))
        self.assertEqual(sorted(result.returncode == 0 for result in results), [False, True])
        self.assertEqual(len(self.protected_events()), 1)

    def test_auto_targets_disabled(self):
        for target in ("tf-apply-auto", "tf-destroy-auto"):
            self.reset_events()
            self.assertNotEqual(self.call(["ENV=k3s-lab", target], "yes").returncode, 0)
            self.assertEqual(self.protected_events(), [])


if __name__ == "__main__":
    unittest.main()
