#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2015, Maciej Delmanowski <drybjed@gmail.com>
# (c) 2018, Victor da Costa <victorockeiro@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: virt_net
author: "Maciej Delmanowski (@drybjed)"
version_added: "2.0"
short_description: Manage libvirt network configuration
description:
     - Manage I(libvirt) networks.
options:
    name:
        required: true
        aliases: ['network']
        description:
            - name of the network being managed. Note that network must be previously
              defined with xml.
    state:
        required: false
        choices: [ "active", "inactive", "present", "absent" ]
        description:
            - specify which state you want a network to be in.
              If 'active', network will be created and started.
              If 'present', ensure that network is present but do not change its
              state; It's created if missing.
              If 'inactive', network will be stopped.
              If 'absent', network will be stopped and removed from I(libvirt) configuration.
    autostart:
        required: false
        type: bool
        description:
            - Specify if a given network should be started automatically on system boot.
    uri:
        required: false
        default: "qemu:///system"
        description:
            - libvirt connection uri.
    xml:
        required: true
        description:
            - XML document used with the define command.

requirements:
    - "python >= 2.6"
    - "python-libvirt"
    - "python-lxml"
'''

EXAMPLES = '''
# Ensure that a network is active (needs to be defined and built first)
- virt_net:
    state: active
    xml: "{{ lookup('template', 'network-template.xml.j2') }}"
    name: br_nat

# Ensure that a network is inactive
- virt_net:
    state: inactive
    xml: "{{ lookup('template', 'network-template.xml.j2') }}"
    name: br_nat

# Ensure that a given network will be started at boot
- virt_net:
    state: active
    xml: "{{ lookup('template', 'network-template.xml.j2') }}"
    name: br_nat
    autostart: yes

# Ensure that a given network will be started at boot
- virt_net:
    state: active
    xml: "{{ lookup('template', 'network-template.xml.j2') }}"
    name: br_nat
    autostart: no

'''

try:
    import libvirt
except ImportError:
    HAS_VIRT = False
else:
    HAS_VIRT = True

try:
    from lxml import etree
except ImportError:
    HAS_XML = False
else:
    HAS_XML = True

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native


VIRT_FAILED = 1
VIRT_SUCCESS = 0
VIRT_UNAVAILABLE = 2

STATES = [ 'present', 'absent', 'active', 'inactive' ]

ENTRY_STATE_ACTIVE_MAP = {
    0: "inactive",
    1: "active"
}

ENTRY_STATE_AUTOSTART_MAP = {
    0: "no",
    1: "yes"
}

ENTRY_STATE_PERSISTENT_MAP = {
    0: "no",
    1: "yes"
}


class EntryNotFound(Exception):
    pass


class LibvirtConnection(object):

    def __init__(self, uri, module):

        self.module = module

        conn = libvirt.open(uri)

        if not conn:
            raise Exception("hypervisor connection failure")

        self.conn = conn

    def find_entry(self, entryid):
        # entryid = -1 returns a list of everything

        results = []

        # Get active entries
        for name in self.conn.listNetworks():
            entry = self.conn.networkLookupByName(name)
            results.append(entry)

        # Get inactive entries
        for name in self.conn.listDefinedNetworks():
            entry = self.conn.networkLookupByName(name)
            results.append(entry)

        if entryid == -1:
            return results

        for entry in results:
            if entry.name() == entryid:
                return entry

        raise EntryNotFound("network %s not found" % entryid)

    def create(self, entryid):
        if not self.module.check_mode:
            return self.find_entry(entryid).create()
        else:
            try:
                state = self.find_entry(entryid).isActive()
            except:
                return self.module.exit_json(changed=True)
            if not state:
                return self.module.exit_json(changed=True)

    def modify(self, entryid, xml):
        network = self.find_entry(entryid)
        # identify what type of entry is given in the xml
        new_data = etree.fromstring(xml)
        old_data = etree.fromstring(network.XMLDesc(0))
        if new_data.tag == 'host':
            mac_addr = new_data.get('mac')
            hosts = old_data.xpath('/network/ip/dhcp/host')
            # find the one mac we're looking for
            host = None
            for h in hosts:
                if h.get('mac') == mac_addr:
                    host = h
                    break
            if host is None:
                # add the host
                if not self.module.check_mode:
                    res = network.update(libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_LAST,
                                         libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
                                         -1, xml, libvirt.VIR_NETWORK_UPDATE_AFFECT_CURRENT)
                else:
                    # pretend there was a change
                    res = 0
                if res == 0:
                    return True
            else:
                # change the host
                if host.get('name') == new_data.get('name') and host.get('ip') == new_data.get('ip'):
                    return False
                else:
                    if not self.module.check_mode:
                        res = network.update(libvirt.VIR_NETWORK_UPDATE_COMMAND_MODIFY,
                                             libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST,
                                             -1, xml, libvirt.VIR_NETWORK_UPDATE_AFFECT_CURRENT)
                    else:
                        # pretend there was a change
                        res = 0
                    if res == 0:
                        return True
            #  command, section, parentIndex, xml, flags=0
            self.module.fail_json(msg='updating this is not supported yet %s' % to_native(xml))

    def destroy(self, entryid):
        if not self.module.check_mode:
            return self.find_entry(entryid).destroy()
        else:
            if self.find_entry(entryid).isActive():
                return self.module.exit_json(changed=True)

    def undefine(self, entryid):
        if not self.module.check_mode:
            return self.find_entry(entryid).undefine()
        else:
            if not self.find_entry(entryid):
                return self.module.exit_json(changed=True)

    def get_status2(self, entry):
        state = entry.isActive()
        return ENTRY_STATE_ACTIVE_MAP.get(state, "unknown")

    def get_status(self, entryid):
        if not self.module.check_mode:
            state = self.find_entry(entryid).isActive()
            return ENTRY_STATE_ACTIVE_MAP.get(state, "unknown")
        else:
            try:
                state = self.find_entry(entryid).isActive()
                return ENTRY_STATE_ACTIVE_MAP.get(state, "unknown")
            except:
                return ENTRY_STATE_ACTIVE_MAP.get("inactive", "unknown")

    def get_uuid(self, entryid):
        return self.find_entry(entryid).UUIDString()

    def get_xml(self, entryid):
        return self.find_entry(entryid).XMLDesc(0)

    def get_forward(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        try:
            result = xml.xpath('/network/forward')[0].get('mode')
        except:
            raise ValueError('Forward mode not specified')
        return result

    def get_domain(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        try:
            result = xml.xpath('/network/domain')[0].get('name')
        except:
            raise ValueError('Domain not specified')
        return result

    def get_macaddress(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        try:
            result = xml.xpath('/network/mac')[0].get('address')
        except:
            raise ValueError('MAC address not specified')
        return result

    def get_autostart(self, entryid):
        state = self.find_entry(entryid).autostart()
        return ENTRY_STATE_AUTOSTART_MAP.get(state, "unknown")

    def get_autostart2(self, entryid):
        if not self.module.check_mode:
            return self.find_entry(entryid).autostart()
        else:
            try:
                return self.find_entry(entryid).autostart()
            except:
                return self.module.exit_json(changed=True)

    def set_autostart(self, entryid, val):
        if not self.module.check_mode:
            return self.find_entry(entryid).setAutostart(val)
        else:
            try:
                state = self.find_entry(entryid).autostart()
            except:
                return self.module.exit_json(changed=True)
            if bool(state) != val:
                return self.module.exit_json(changed=True)

    def get_bridge(self, entryid):
        return self.find_entry(entryid).bridgeName()

    def get_persistent(self, entryid):
        state = self.find_entry(entryid).isPersistent()
        return ENTRY_STATE_PERSISTENT_MAP.get(state, "unknown")

    def get_dhcp_leases(self, entryid):
        network = self.find_entry(entryid)
        return network.DHCPLeases()

    def define_from_xml(self, entryid, xml):
        if not self.module.check_mode:
            return self.conn.networkDefineXML(xml)
        else:
            try:
                self.find_entry(entryid)
            except:
                return self.module.exit_json(changed=True)


class VirtNetwork(object):

    def __init__(self, uri, module):
        self.module = module
        self.uri = uri
        self.conn = LibvirtConnection(self.uri, self.module)

    def get_net(self, entryid):
        return self.conn.find_entry(entryid)

    def list_nets(self, state=None):
        results = []
        for entry in self.conn.find_entry(-1):
            if state:
                if state == self.conn.get_status2(entry):
                    results.append(entry.name())
            else:
                results.append(entry.name())
        return results

    def state(self):
        results = []
        for entry in self.list_nets():
            state_blurb = self.conn.get_status(entry)
            results.append("%s %s" % (entry, state_blurb))
        return results

    def autostart(self, entryid):
        return self.conn.set_autostart(entryid, True)

    def get_autostart(self, entryid):
        return self.conn.get_autostart2(entryid)

    def set_autostart(self, entryid, state):
        return self.conn.set_autostart(entryid, state)

    def create(self, entryid):
        return self.conn.create(entryid)

    def modify(self, entryid, xml):
        return self.conn.modify(entryid, xml)

    def start(self, entryid):
        return self.conn.create(entryid)

    def stop(self, entryid):
        return self.conn.destroy(entryid)

    def destroy(self, entryid):
        return self.conn.destroy(entryid)

    def undefine(self, entryid):
        return self.conn.undefine(entryid)

    def status(self, entryid):
        return self.conn.get_status(entryid)

    def get_xml(self, entryid):
        return self.conn.get_xml(entryid)

    def define(self, entryid, xml):
        return self.conn.define_from_xml(entryid, xml)

    def info(self):
        return self.facts(facts_mode='info')

    def facts(self, facts_mode='facts'):
        results = dict()
        for entry in self.list_nets():
            results[entry] = dict()
            results[entry]["autostart"] = self.conn.get_autostart(entry)
            results[entry]["persistent"] = self.conn.get_persistent(entry)
            results[entry]["state"] = self.conn.get_status(entry)
            results[entry]["bridge"] = self.conn.get_bridge(entry)
            results[entry]["uuid"] = self.conn.get_uuid(entry)
            try:
                results[entry]["dhcp_leases"] = self.conn.get_dhcp_leases(entry)
            # not supported on RHEL 6
            except AttributeError:
                pass

            try:
                results[entry]["forward_mode"] = self.conn.get_forward(entry)
            except ValueError:
                pass

            try:
                results[entry]["domain"] = self.conn.get_domain(entry)
            except ValueError:
                pass

            try:
                results[entry]["macaddress"] = self.conn.get_macaddress(entry)
            except ValueError:
                pass

        facts = dict()
        if facts_mode == 'facts':
            facts["ansible_facts"] = dict()
            facts["ansible_facts"]["ansible_libvirt_networks"] = results
        elif facts_mode == 'info':
            facts['networks'] = results
        return facts

class NetworkStateMachine(object):
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


    def present(self):
        try:
            self._result['msg'] = self._virt.find_entry(self._guest)

        except Exception as e:
            self._result['msg'] = self._virt.define(self._xml)
            self._result['changed'] = True

        else:
            self.result['changed'] = False

        finally:
            return self

    def absent(self):
        try:
            self._result['msg'] = self._virt.find_entry(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
            self.shutdown().result['msg'] = self._virt.undefine(self._guest)
            self._result['changed'] = True

        finally:
            return self

    def active(self):
        try:
            self._result['msg'] = virt.start(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
            self._result['changed'] = True

        finally:
            return self

    def inactive(self):
        try:
            self._result['msg'] = self._virt.stop(self._guest)

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


def core(module):
    virt    = Virt(module)
    fsm     = NetworkStateMachine(virt, module)
    state   = module.params.get('state')

    if state == 'present':
        return fsm.start().present().autostart().end()

    elif state == 'active':
        return fsm.start().present().autostart().active().end()

    elif state == 'inactive':
        return fsm.start().present().autostart().inactive().end()

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
        supports_check_mode=True
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
