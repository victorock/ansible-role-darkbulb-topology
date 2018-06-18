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
module: virt_pool
author: "Maciej Delmanowski (@drybjed)"
version_added: "2.0"
short_description: Manage libvirt storage pools
description:
    - Manage I(libvirt) storage pools.
options:
    name:
        required: false
        aliases: [ "pool" ]
        description:
            - name of the storage pool being managed. Note that pool must be previously
              defined with xml.
    state:
        required: false
        choices: [ "active", "inactive", "present", "absent" ]
        description:
            - specify which state you want a storage pool to be in.
              If 'active', pool will be created and started.
              If 'present', ensure that pool is present but do not change its
              state; It's created if missing.
              If 'inactive', pool will be stopped.
              If 'absent', pool will be inactivated and removed from I(libvirt) configuration without cleaning).
              If 'cleaned', pool contents will be deleted, inactivated and removed from I(libvirt).
    autostart:
        required: false
        type: bool
        description:
            - Specify if a given storage pool should be started automatically on system boot.
    uri:
        required: false
        default: "qemu:///system"
        description:
            - I(libvirt) connection uri.
    xml:
        required: false
        description:
            - XML document used with the define command.
    mode:
        required: false
        choices: [ 'new', 'repair', 'resize', 'no_overwrite', 'overwrite', 'normal', 'zeroed' ]
        description:
            - Pass additional parameters to 'build' or 'delete' commands.
requirements:
    - "python >= 2.6"
    - "python-libvirt"
    - "python-lxml"
'''

EXAMPLES = '''
# Ensure that a storagepool is active (needs to be defined and built first)
- virt_pool:
    state: active
    xml: "{{ lookup('template', 'pool01-template.xml.j2') }}"
    name: pool01

# Ensure that a storagepool is inactive
- virt_pool:
    state: inactive
    xml: "{{ lookup('template', 'pool01-template.xml.j2') }}"
    name: pool01

# Ensure that a given storagepool will be started at boot
- virt_pool:
    state: active
    xml: "{{ lookup('template', 'pool01-template.xml.j2') }}"
    name: pool01
    autostart: yes

# Ensure that a given storagepool will be started at boot
- virt_pool:
    state: active
    xml: "{{ lookup('template', 'pool01-template.xml.j2') }}"
    name: pool01
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

ENTRY_STATE_INFO_MAP = {
    0: "inactive",
    1: "building",
    2: "running",
    3: "degraded",
    4: "inaccessible"
}

ENTRY_BUILD_FLAGS_MAP = {
    "new": 0,
    "repair": 1,
    "resize": 2,
    "no_overwrite": 4,
    "overwrite": 8
}

ENTRY_DELETE_FLAGS_MAP = {
    "normal": 0,
    "zeroed": 1
}

ALL_MODES = []
ALL_MODES.extend(ENTRY_BUILD_FLAGS_MAP.keys())
ALL_MODES.extend(ENTRY_DELETE_FLAGS_MAP.keys())


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
        for name in self.conn.listStoragePools():
            entry = self.conn.storagePoolLookupByName(name)
            results.append(entry)

        # Get inactive entries
        for name in self.conn.listDefinedStoragePools():
            entry = self.conn.storagePoolLookupByName(name)
            results.append(entry)

        if entryid == -1:
            return results

        for entry in results:
            if entry.name() == entryid:
                return entry

        raise EntryNotFound("storage pool %s not found" % entryid)

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

    def get_info(self, entryid):
        return self.find_entry(entryid).info()

    def get_volume_count(self, entryid):
        return self.find_entry(entryid).numOfVolumes()

    def get_volume_names(self, entryid):
        return self.find_entry(entryid).listVolumes()

    def get_devices(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        if xml.xpath('/pool/source/device'):
            result = []
            for device in xml.xpath('/pool/source/device'):
                result.append(device.get('path'))
        try:
            return result
        except:
            raise ValueError('No devices specified')

    def get_format(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        try:
            result = xml.xpath('/pool/source/format')[0].get('type')
        except:
            raise ValueError('Format not specified')
        return result

    def get_host(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        try:
            result = xml.xpath('/pool/source/host')[0].get('name')
        except:
            raise ValueError('Host not specified')
        return result

    def get_source_path(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        try:
            result = xml.xpath('/pool/source/dir')[0].get('path')
        except:
            raise ValueError('Source path not specified')
        return result

    def get_path(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        return xml.xpath('/pool/target/path')[0].text

    def get_type(self, entryid):
        xml = etree.fromstring(self.find_entry(entryid).XMLDesc(0))
        return xml.get('type')

    def build(self, entryid, flags):
        if not self.module.check_mode:
            return self.find_entry(entryid).build(flags)
        else:
            try:
                state = self.find_entry(entryid)
            except:
                return self.module.exit_json(changed=True)
            if not state:
                return self.module.exit_json(changed=True)

    def delete(self, entryid, flags):
        if not self.module.check_mode:
            return self.find_entry(entryid).delete(flags)
        else:
            try:
                state = self.find_entry(entryid)
            except:
                return self.module.exit_json(changed=True)
            if state:
                return self.module.exit_json(changed=True)

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

    def refresh(self, entryid):
        return self.find_entry(entryid).refresh()

    def get_persistent(self, entryid):
        state = self.find_entry(entryid).isPersistent()
        return ENTRY_STATE_PERSISTENT_MAP.get(state, "unknown")

    def define_from_xml(self, entryid, xml):
        if not self.module.check_mode:
            return self.conn.storagePoolDefineXML(xml)
        else:
            try:
                self.find_entry(entryid)
            except:
                return self.module.exit_json(changed=True)


class VirtStoragePool(object):

    def __init__(self, uri, module):
        self.module = module
        self.uri = uri
        self.conn = LibvirtConnection(self.uri, self.module)

    def get_pool(self, entryid):
        return self.conn.find_entry(entryid)

    def list_pools(self, state=None):
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
        for entry in self.list_pools():
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

    def build(self, entryid, flags):
        return self.conn.build(entryid, ENTRY_BUILD_FLAGS_MAP.get(flags, 0))

    def delete(self, entryid, flags):
        return self.conn.delete(entryid, ENTRY_DELETE_FLAGS_MAP.get(flags, 0))

    def refresh(self, entryid):
        return self.conn.refresh(entryid)

    def info(self):
        return self.facts(facts_mode='info')

    def facts(self, facts_mode='facts'):
        results = dict()
        for entry in self.list_pools():
            results[entry] = dict()
            if self.conn.find_entry(entry):
                data = self.conn.get_info(entry)
                # libvirt returns maxMem, memory, and cpuTime as long()'s, which
                # xmlrpclib tries to convert to regular int's during serialization.
                # This throws exceptions, so convert them to strings here and
                # assume the other end of the xmlrpc connection can figure things
                # out or doesn't care.
                results[entry] = {
                    "status": ENTRY_STATE_INFO_MAP.get(data[0], "unknown"),
                    "size_total": str(data[1]),
                    "size_used": str(data[2]),
                    "size_available": str(data[3]),
                }
                results[entry]["autostart"] = self.conn.get_autostart(entry)
                results[entry]["persistent"] = self.conn.get_persistent(entry)
                results[entry]["state"] = self.conn.get_status(entry)
                results[entry]["path"] = self.conn.get_path(entry)
                results[entry]["type"] = self.conn.get_type(entry)
                results[entry]["uuid"] = self.conn.get_uuid(entry)
                if self.conn.find_entry(entry).isActive():
                    results[entry]["volume_count"] = self.conn.get_volume_count(entry)
                    results[entry]["volumes"] = list()
                    for volume in self.conn.get_volume_names(entry):
                        results[entry]["volumes"].append(volume)
                else:
                    results[entry]["volume_count"] = -1

                try:
                    results[entry]["host"] = self.conn.get_host(entry)
                except ValueError:
                    pass

                try:
                    results[entry]["source_path"] = self.conn.get_source_path(entry)
                except ValueError:
                    pass

                try:
                    results[entry]["format"] = self.conn.get_format(entry)
                except ValueError:
                    pass

                try:
                    devices = self.conn.get_devices(entry)
                    results[entry]["devices"] = devices
                except ValueError:
                    pass

            else:
                results[entry]["state"] = self.conn.get_status(entry)

        facts = dict()
        if facts_mode == 'facts':
            facts["ansible_facts"] = dict()
            facts["ansible_facts"]["ansible_libvirt_pools"] = results
        elif facts_mode == 'info':
            facts['pools'] = results
        return facts

class StoragePoolStateMachine(object):
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

    def clean(self):
        try:
            self._result['msg'] = virt.delete(self._guest)

        except Exception as e:
            self._result['changed'] = False

        else:
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
    fsm     = StoragePoolStateMachine(virt, module)
    state   = module.params.get('state')

    if state == 'present':
        return fsm.start().present().autostart().end()

    elif state == 'active':
        return fsm.start().present().autostart().active().end()

    elif state == 'inactive':
        return fsm.start().present().autostart().inactive().end()

    elif state == 'cleaned':
        return fsm.start().absent().clean().end()

    elif state == 'absent':
        return fsm.start().inactive().absent().end()

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
