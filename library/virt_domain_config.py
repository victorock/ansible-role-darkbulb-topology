#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2018 Red Hat, Inc
# Victor da Costa <victorockeiro@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: virt
short_description: Manages virtual machines supported by libvirt
description:
     - Manages virtual machines supported by I(libvirt).
version_added: "0.2"
options:
  name:
    description:
      - name of the guest VM being managed. Note that VM must be previously
        defined with xml.
    required: true
  state:
    description:
      - Note that there may be some lag for state requests like C(shutdown)
        since these refer only to VM states. After starting a guest, it may not
        be immediately accessible.
    choices: [ 'present', 'absent', 'running', 'shutdown', 'poweredoff', 'paused' ]
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
    description:
      - XML document used with the define command.
      - Must be raw XML content using C(lookup). XML cannot be reference to a file.
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
    description: The status of the VM, among running, crashed, paused and shutdown
    type: string
    sample: "success"
    returned: success
'''
import traceback

from ansible.errors import AnsibleError
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native
from ansible.module_utils.virt import VirtDomain

try:
    import libvirt
except:
    raise AnsibleError("Module virt_domain_config requires libvirt. try: pip install libvirt")

try:
    import xmltodict
except:
    raise AnsibleError("Module virt_domain_config requires xmltodict. try: pip install xmltodict")


STATES = [ 'present', 'absent', 'started', 'stopped', 'poweredoff', 'paused', 'unpaused' ]


class ComputeStateMachine():
    def __init__(self, module):
        self._module        = module
        self._uri           = self._module.params.get('uri')
        self._format        = self._module.params.get('format')
        self._spec          = self._module.params.get('spec')
        self._state         = self._module.params.get('state')
        self._results       = []

        return self.state()

    def state(self):
        try:
            return getattr(self, self._state)()

        except AttributeError:
            e = "Unsupported state {state}".format(state=self._state)
            self._module.fail_json(msg=to_native(e), exception=traceback.format_exc())

    def process(self, task):
        self._results.append(task)
        return self.done()

    def done(self):
        for result in self._results:
            if result['changed']:
                return result
        return self._results.pop()

    def present(self):
        with VirtDomain(self._uri, self._spec, self._format) as virt:
            self.process(virt.define())
            return self.done()

    def absent(self):
        with VirtDomain(self._uri, self._spec, self._format) as virt:
            self.process(virt.undefine())
            return self.done()

    def started(self):
        with VirtDomain(self._uri, self._spec, self._format) as virt:
            self.present()
            self.unpaused()
            self.process(virt.start())
            return self.done()

    def stopped(self):
        with VirtDomain(self._uri, self._spec, self._format) as virt:
            self.process(virt.shutdown())
            return self.done()

    def poweredoff(self):
        with VirtDomain(self._uri, self._spec, self._format) as virt:
            self.process(virt.poweroff())
            return self.done()

    def paused(self):
        with VirtDomain(self._uri, self._spec, self._format) as virt:
            self.process(virt.pause())
            return self.done()

    def unpaused(self):
        with VirtDomain(self._uri, self._spec, self._format) as virt:
            self.process(virt.unpause())
            return self.done()

def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(type='str', default='present', choices=STATES),
            uri=dict(type='str', default='qemu:///system'),
            spec=dict(required=True, type='str', default=None),
            format=dict(type='str', default='xml'),
            backup=dict(type='bool', default=False),
        ),
    )

    try:
        csm = ComputeStateMachine(module)
        result = csm.state()

    except Exception as e:
        module.fail_json(msg=to_native(e), exception=traceback.format_exc())

    else:
        module.exit_json(**result)

if __name__ == '__main__':
    main()
