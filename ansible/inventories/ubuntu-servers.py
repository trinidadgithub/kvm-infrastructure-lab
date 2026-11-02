#!/usr/bin/env python3
"""Inventory from the ubuntu-servers root's declared vm_ips output."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "environments" / "ubuntu-servers"


def main():
    if not (len(sys.argv) == 2 and sys.argv[1] == "--list") and not (
        len(sys.argv) == 3 and sys.argv[1] == "--host"
    ):
        print("Usage: ubuntu-servers.py --list | --host NAME", file=sys.stderr)
        return 1

    fixture = os.environ.get("UBUNTU_SERVERS_OUTPUTS_FILE")
    if fixture:
        outputs = json.loads(Path(fixture).read_text(encoding="utf-8"))
    else:
        result = subprocess.run(
            ["terraform", f"-chdir={ROOT}", "output", "-json"],
            capture_output=True,
            text=True,
            check=True,
        )
        outputs = json.loads(result.stdout)

    ips = outputs["vm_ips"]["value"]
    if not isinstance(ips, dict) or not ips:
        raise ValueError("vm_ips output must be a nonempty map; apply this root before using live inventory")

    if sys.argv[1] == "--host":
        print(json.dumps({"ansible_host": ips[sys.argv[2]]} if sys.argv[2] in ips else {}))
        return 0

    group_vars = {
        "ansible_user": "ubuntu",
        "ansible_python_interpreter": "/usr/bin/python3",
    }

    if os.environ.get("ANSIBLE_PRIVATE_KEY_FILE"):
        group_vars["ansible_ssh_private_key_file"] = os.environ["ANSIBLE_PRIVATE_KEY_FILE"]

    print(json.dumps({
        "ubuntu_servers": {"hosts": sorted(ips), "vars": group_vars},
        "_meta": {"hostvars": {name: {"ansible_host": ip} for name, ip in ips.items()}},
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ubuntu-servers inventory: {exc}", file=sys.stderr)
        sys.exit(1)
