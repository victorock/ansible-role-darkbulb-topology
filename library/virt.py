#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2007, 2012 Red Hat, Inc
# Michael DeHaan <michael.dehaan@gmail.com>
# Seth Vidal <skvidal@fedoraproject.org>
# Victor da Costa <victorockeiro@gmail.com>
# GNU General Public License v3.0+
#   (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import traceback
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native
from ansible.module_utils.virt import DOMAIN_STATES, ALL_COMMANDS
from ansible.module_utils.virt import core, VIRT_SUCCESS

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: virt
short_description: Manages virtual machines supported by libvirt
comments:
     - Manages virtual machines supported by I(libvirt).
version_added: "0.2"
options:
  name:
    comments: |
        name of the guest VM being managed.
        Note that name must match the domain name defined in the xml.
    required: true
  state:
    choices:
        - 'present'
        - 'destroyed'
        - 'absent'
        - 'running'
        - 'stopped'
        - 'poweredoff'
        - 'paused'
    comments:
        - `present` = Ensure that domain is `present` without changing the current state.
        - `absent` = Ensure that domain is `absent`.
        - `running` = Ensure that `present` domains are `running`.
        - `stopped` = Ensure that `running` domains are `shutdown` (try gracefully first).
        - `poweredoff` = Ensure that `running` domains are `shutdown` (non-gracefully).
        - `paused` = ensure `running` domains are paused.
        - `destroyed` = `shutdown` = `stopped`.
  autostart:
    description:
      - start VM at host startup.
    type: bool
    version_added: "2.3"
  uri:
    description:
      - libvirt connection uri.
    default: qemu:///system
  xml:
    required: false
    type: string
    comments:
      - XML document used with the states.
      - Must be raw XML content using C(lookup).
      - XML cannot be reference to a file.
requirements:
    - python >= 2.6
    - libvirt-python
author:
    - Ansible Core Team
    - Michael DeHaan
    - Seth Vidal
    - Victor da Costa
'''

EXAMPLES = '''
# a playbook task line:
- virt:
    name: alpha
    xml: "{{ lookup('template', 'machine-template.xml.j2') }}"
    state: running
'''

RETURN = '''
# for any state
virt: {
    "domains": {
        "leaf01": {
            "autostart": 0,
            "cpuTime": "0",
            "maxMem": "8388608",
            "memory": "8388608",
            "nrVirtCpu": "2",
            "state": "shutdown"
        },
        "leaf02": {
            "autostart": 0,
            "cpuTime": "0",
            "maxMem": "8388608",
            "memory": "8388608",
            "nrVirtCpu": "2",
            "state": "shutdown"
        },
        "leaf03": {
            "autostart": 0,
            "cpuTime": "0",
            "maxMem": "8388608",
            "memory": "8388608",
            "nrVirtCpu": "2",
            "state": "shutdown"
        },
        "leaf04": {
            "autostart": 0,
            "cpuTime": "0",
            "maxMem": "8388608",
            "memory": "8388608",
            "nrVirtCpu": "2",
            "state": "shutdown"
        }
    },
    "node": {
        "cpucores": "8",
        "cpumhz": "2300",
        "cpumodel": "x86_64",
        "cpus": "16",
        "cputhreads": "2",
        "numanodes": "1",
        "phymemory": "61439",
        "sockets": "1"
    }
}

# for list_vms command
list_vms:
    description: The list of vms defined on the remote system
    type: dictionary
    returned: success
    sample: [
        "build.example.org",
        "dev.example.org"
    ]
# for status command
status:
    description:
        - The status of the VM, among running, crashed, paused and shutdown
    type: string
    sample: "success"
    returned: success
'''

try:
    import libvirt
except ImportError:
    HAS_VIRT = False
else:
    HAS_VIRT = True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(required=True, type='str', aliases=['guest']),
            state=dict(type='str', choices=DOMAIN_STATES),
            command=dict(type='str', choices=ALL_COMMANDS),
            autostart=dict(type='bool', default=False),
            uri=dict(type='str', default='qemu:///system'),
            xml=dict(required=False, type='str'),
        ),
        mutually_exclusive=[
            ["command", "state"]
        ],
        required_one_of=[
            ["command", "state"]
        ],
        required_if=[
            ["state", "present", ["xml"]],
            ["command", "define", ["xml"]]
        ]
    )

    if not HAS_VIRT:
        module.fail_json(msg=(
                'The `libvirt` module is not importable.'
                'Check the requirements.'
            )
        )

    rc = VIRT_SUCCESS
    try:
        rc, result = core(module)
    except Exception as e:
        module.fail_json(msg=to_native(e), exception=traceback.format_exc())

    if rc != 0:  # something went wrong emit the msg
        module.fail_json(rc=rc, msg=result)
    else:
        module.exit_json(**result)


if __name__ == '__main__':
    main()
