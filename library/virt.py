#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2007, 2012 Red Hat, Inc
# Michael DeHaan <michael.dehaan@gmail.com>
# Seth Vidal <skvidal@fedoraproject.org>
# Victor da Costa <victorockeiro@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
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

try:
    import libvirt
except ImportError:
    HAS_VIRT = False
else:
    HAS_VIRT = True

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native


VIRT_FAILED = 1
VIRT_SUCCESS = 0
VIRT_UNAVAILABLE = 2

STATES = [ 'present', 'absent', 'running', 'shutdown', 'poweredoff', 'paused' ]

VIRT_STATE_NAME_MAP = {
    0: 'running',
    1: 'running',
    2: 'running',
    3: 'paused',
    4: 'shutdown',
    5: 'shutdown',
    6: 'crashed',
}


class VMNotFound(Exception):
    pass


class LibvirtConnection(object):

    def __init__(self, uri, module):

        self.module = module

        cmd = "uname -r"
        rc, stdout, stderr = self.module.run_command(cmd)

        if "xen" in stdout:
            conn = libvirt.open(None)
        elif "esx" in uri:
            auth = [[libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_NOECHOPROMPT], [], None]
            conn = libvirt.openAuth(uri, auth)
        else:
            conn = libvirt.open(uri)

        if not conn:
            raise Exception("hypervisor connection failure")

        self.conn = conn

    def find_vm(self, vmid):
        """
        Extra bonus feature: vmid = -1 returns a list of everything
        """
        conn = self.conn

        vms = []

        # this block of code borrowed from virt-manager:
        # get working domain's name
        ids = conn.listDomainsID()
        for id in ids:
            vm = conn.lookupByID(id)
            vms.append(vm)
        # get defined domain
        names = conn.listDefinedDomains()
        for name in names:
            vm = conn.lookupByName(name)
            vms.append(vm)

        if vmid == -1:
            return vms

        for vm in vms:
            if vm.name() == vmid:
                return vm

        raise VMNotFound("virtual machine %s not found" % vmid)

    def shutdown(self, vmid):
        return self.find_vm(vmid).shutdown()

    def pause(self, vmid):
        return self.suspend(vmid)

    def unpause(self, vmid):
        return self.resume(vmid)

    def suspend(self, vmid):
        return self.find_vm(vmid).suspend()

    def resume(self, vmid):
        return self.find_vm(vmid).resume()

    def create(self, vmid):
        return self.find_vm(vmid).create()

    def destroy(self, vmid):
        return self.find_vm(vmid).destroy()

    def undefine(self, vmid):
        return self.find_vm(vmid).undefine()

    def get_status2(self, vm):
        state = vm.info()[0]
        return VIRT_STATE_NAME_MAP.get(state, "unknown")

    def get_status(self, vmid):
        state = self.find_vm(vmid).info()[0]
        return VIRT_STATE_NAME_MAP.get(state, "unknown")

    def nodeinfo(self):
        return self.conn.getInfo()

    def get_type(self):
        return self.conn.getType()

    def get_xml(self, vmid):
        vm = self.conn.lookupByName(vmid)
        return vm.XMLDesc(0)

    def get_maxVcpus(self, vmid):
        vm = self.conn.lookupByName(vmid)
        return vm.maxVcpus()

    def get_maxMemory(self, vmid):
        vm = self.conn.lookupByName(vmid)
        return vm.maxMemory()

    def getFreeMemory(self):
        return self.conn.getFreeMemory()

    def get_autostart(self, vmid):
        vm = self.conn.lookupByName(vmid)
        return vm.autostart()

    def set_autostart(self, vmid, val):
        vm = self.conn.lookupByName(vmid)
        return vm.setAutostart(val)

    def define_from_xml(self, xml):
        return self.conn.defineXML(xml)


class Virt(object):

    def __init__(self, module):
        self.module = module
        self.uri = module.params.get('uri')

    def __get_conn(self):
        self.conn = LibvirtConnection(self.uri, self.module)
        return self.conn

    def get_vm(self, vmid):
        self.__get_conn()
        return self.conn.find_vm(vmid)

    def state(self):
        vms = self.list_vms()
        state = []
        for vm in vms:
            state_blurb = self.conn.get_status(vm)
            state.append("%s %s" % (vm, state_blurb))
        return state

    def info(self):
        vms = self.list_vms()
        info = dict()
        for vm in vms:
            data = self.conn.find_vm(vm).info()
            # libvirt returns maxMem, memory, and cpuTime as long()'s, which
            # xmlrpclib tries to convert to regular int's during serialization.
            # This throws exceptions, so convert them to strings here and
            # assume the other end of the xmlrpc connection can figure things
            # out or doesn't care.
            info[vm] = dict(
                state=VIRT_STATE_NAME_MAP.get(data[0], "unknown"),
                maxMem=str(data[1]),
                memory=str(data[2]),
                nrVirtCpu=data[3],
                cpuTime=str(data[4]),
                autostart=self.conn.get_autostart(vm),
            )

        return info

    def nodeinfo(self):
        self.__get_conn()
        data = self.conn.nodeinfo()
        info = dict(
            cpumodel=str(data[0]),
            phymemory=str(data[1]),
            cpus=str(data[2]),
            cpumhz=str(data[3]),
            numanodes=str(data[4]),
            sockets=str(data[5]),
            cpucores=str(data[6]),
            cputhreads=str(data[7])
        )
        return info

    def list_vms(self, state=None):
        self.conn = self.__get_conn()
        vms = self.conn.find_vm(-1)
        results = []
        for x in vms:
            try:
                if state:
                    vmstate = self.conn.get_status2(x)
                    if vmstate == state:
                        results.append(x.name())
                else:
                    results.append(x.name())
            except:
                pass
        return results

    def virttype(self):
        return self.__get_conn().get_type()

    def autostart(self, vmid, as_flag):
        self.conn = self.__get_conn()
        # Change autostart flag only if needed
        if self.conn.get_autostart(vmid) != as_flag:
            self.conn.set_autostart(vmid, as_flag)
            return True

        return False

    def freemem(self):
        self.conn = self.__get_conn()
        return self.conn.getFreeMemory()

    def shutdown(self, vmid):
        """ Make the machine with the given vmid stop running.  Whatever that takes.  """
        self.__get_conn()
        self.conn.shutdown(vmid)
        return 0

    def pause(self, vmid):
        """ Pause the machine with the given vmid.  """

        self.__get_conn()
        return self.conn.suspend(vmid)

    def unpause(self, vmid):
        """ Unpause the machine with the given vmid.  """

        self.__get_conn()
        return self.conn.resume(vmid)

    def create(self, vmid):
        """ Start the machine via the given vmid """

        self.__get_conn()
        return self.conn.create(vmid)

    def start(self, vmid):
        """ Start the machine via the given id/name """

        self.__get_conn()
        return self.conn.create(vmid)

    def destroy(self, vmid):
        """ Pull the virtual power from the virtual domain, giving it virtually no time to virtually shut down.  """
        self.__get_conn()
        return self.conn.destroy(vmid)

    def undefine(self, vmid):
        """ Stop a domain, and then wipe it from the face of the earth.  (delete disk/config file) """

        self.__get_conn()
        return self.conn.undefine(vmid)

    def status(self, vmid):
        """
        Return a state suitable for server consumption.  Aka, codes.py values, not XM output.
        """
        self.__get_conn()
        return self.conn.get_status(vmid)

    def get_xml(self, vmid):
        """
        Receive a Vm id as input
        Return an xml describing vm config returned by a libvirt call
        """

        self.__get_conn()
        return self.conn.get_xml(vmid)

    def get_maxVcpus(self, vmid):
        """
        Gets the max number of VCPUs on a guest
        """

        self.__get_conn()
        return self.conn.get_maxVcpus(vmid)

    def get_max_memory(self, vmid):
        """
        Gets the max memory on a guest
        """

        self.__get_conn()
        return self.conn.get_MaxMemory(vmid)

    def define(self, xml):
        """
        Define a guest with the given xml
        """
        self.__get_conn()
        return self.conn.define_from_xml(xml)

class ComputeStateMachine(object):
    def __init__(self, virt, module):
        self._result     = dict()
        self._virt       = virt
        self._module     = module
        self._guest      = module.params.get('name')
        self._xml        = module.params.get('xml')
        self._autostart  = module.params.get('autostart')

    @property
    def result(self):
        return self._result

    def start(self):
        return self

    def end(self):
        return self.result

    def absent(self):
        try:
            self._result['msg'] = self._virt.find_vm(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
            self.shutdown().result['msg'] = self._virt.undefine(self._guest)
            self._result['changed'] = True

        finally:
            return self

    def shutdown(self):
        try:
            self._result['msg'] = self._virt.shutdown(self._guest)

        except Exception as e:
            self._result['changed']   = False

        else:
            self._result['changed'] = True

        finally:
            return self

    def define(self):
        try:
            self._result['msg'] = self._virt.define(self._xml)

        except Exception as e:
            self._result['changed'] = False

        else:
            self._result['changed'] = True

        finally:
            return self

    def present(self):
        try:
            self._result['msg'] = self._virt.find_vm(self._guest)

        except Exception as e:
            self._result['msg'] = self._virt.define(self._xml)
            self._result['changed'] = True

        else:
            self.result['changed'] = False

        finally:
            return self

    def poweroff(self):
        try:
            self._result['msg'] = virt.destroy(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
            self._result['changed'] = True

        finally:
            return self


    def pause(self):
        try:
            self._result['msg'] = self._virt.pause(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
            self._result['changed'] = True

        finally:
            return self


    def unpause(self):
        try:
            self._result['msg'] = self._virt.unpause(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
            self._result['changed'] = True

        finally:
            return self

    def autostart(self):
        try:
            self._result['msg'] = self._virt.autostart(self._guest, self._autostart)

        except Exception as e:
            self._result['changed'] = False

        else:
            self._result['changed'] = True

        finally:
            return self

    def running(self):
        try:
            self._result['msg'] = self._virt.start(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
            self._result['changed'] = True

        finally:
            return self

def core(module):
    virt    = Virt(module)
    fsm     = ComputeStateMachine(virt, module)
    state   = module.params.get('state')

    if state == 'present':
        return fsm.start().present().autostart().end()

    elif state == 'running':
        return fsm.start().present().autostart().unpause().running().end()

    elif state == 'paused':
        return fsm.start().present().autostart().pause().end()

    elif state == 'shutdown':
        return fsm.start().present().autostart().shutdown().end()

    elif state == 'poweredoff':
        return fsm.start().present().autostart().poweroff().end()

    elif state == 'absent':
        return fsm.start().absent().end()

def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(required=True, type='str', aliases=['guest']),
            state=dict(type='str', default='present', choices=STATES),
            autostart=dict(type='bool', default=True),
            uri=dict(type='str', default='qemu:///system'),
            xml=dict(required=True, type='str'),
        ),
    )

    if not HAS_VIRT:
        module.fail_json(msg='The `libvirt` module is not importable. Check the requirements.')

    result = dict()
    try:
        result = core(module)

    except Exception as e:
        module.fail_json(msg=to_native(e), exception=traceback.format_exc())

    finally:
        module.exit_json(**result)

if __name__ == '__main__':
    main()
