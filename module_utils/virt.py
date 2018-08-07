#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2007, 2012 Red Hat, Inc
# Michael DeHaan <michael.dehaan@gmail.com>
# Seth Vidal <skvidal@fedoraproject.org>
# Victor da Costa <victorockeiro@gmail.com>
# GNU General Public License v3.0+
#   (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import traceback
import time

try:
    import libvirt
except ImportError:
    HAS_VIRT = False
else:
    HAS_VIRT = True

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_text, to_bytes


DOMAIN_STATES = [
    'present',
    'absent',
    'running',
    'stopped',
    'poweredoff',
    'paused'
]

DOMAIN_COMMANDS = [
    'create',
    'define',
    'destroy',
    'get_xml',
    'pause',
    'shutdown',
    'status',
    'start',
    'stop',
    'undefine',
    'unpause'
]

NODE_COMMANDS = [
    'freemem',
    'info',
    'list_vms',
    'nodeinfo',
    'virttype'
]

ALL_COMMANDS = []
ALL_COMMANDS.extend(DOMAIN_COMMANDS)
ALL_COMMANDS.extend(NODE_COMMANDS)

# https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainState
VIRT_STATE_NAME_MAP = {
    0: 'running',
    1: 'running',
    2: 'running',
    3: 'paused',
    4: 'shutdown',
    5: 'shutdown',
    6: 'crashed',
}

VIRT_FAILED = 1
VIRT_SUCCESS = 0
VIRT_UNAVAILABLE = 2
VIRT_TIMEOUT = 60


def core(module):
    state = module.params.get('state')
    autostart = module.params.get('autostart')
    guest = module.params.get('name')
    command = module.params.get('command')
    xml = module.params.get('xml')

    v = Virt(module)
    res = dict()

    if state:
        vdsm = VirtDomainStateMachine(module)
        result = getattr(vdsm, state)().result()
        return VIRT_SUCCESS, result

    if command:
        if command in DOMAIN_COMMANDS:
            if not guest:
                module.fail_json(msg="%s requires 1 argument: guest" % command)
            if command == 'define':
                if not xml:
                    module.fail_json(msg="define requires xml argument")
                try:
                    v.get_vm(guest)
                except VMNotFound:
                    v.define(xml)
                    res = {'changed': True, 'created': guest}
                return VIRT_SUCCESS, res
            res = getattr(v, command)(guest)
            if not isinstance(res, dict):
                result = {command: res}
            return VIRT_SUCCESS, res

        elif hasattr(v, command):
            res = getattr(v, command)()
            if not isinstance(res, dict):
                res = {command: res}
            return VIRT_SUCCESS, res

        else:
            module.fail_json(msg="Command %s not recognized" % command)


class VMNotFound(Exception):
    pass


class TransitionTimeoutError(Exception):
    pass


class VirtDomainStateMachineError(Exception):
    pass


class LibvirtConnection(object):

    def __init__(self, uri, module):

        self.module = module

        cmd = "uname -r"
        rc, stdout, stderr = self.module.run_command(cmd)

        if "xen" in stdout:
            conn = libvirt.open(None)
        elif "esx" in uri:
            auth = [
                [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_NOECHOPROMPT],
                [],
                None
            ]
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
        try:
            state = vm.info()[0]
        except VMNotFound:
            return "undefined"
        return VIRT_STATE_NAME_MAP.get(state, "unknown")

    def get_status(self, vmid):
        try:
            state = self.find_vm(vmid).info()[0]
        except VMNotFound:
            return "undefined"
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
            # https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainInfo
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
                nrVirtCpu=str(data[3]),
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
            except Exception:
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
        """
        Make the machine with the given vmid stop running.
        Whatever that takes.
        """
        self.__get_conn()
        return self.conn.shutdown(vmid)

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
        """
        Pull the virtual power from the virtual domain,
        giving it virtually no time to virtually shut down.
        """
        self.__get_conn()
        return self.conn.destroy(vmid)

    def undefine(self, vmid):
        """
        Stop a domain, and then wipe it from the face of the earth.
        (delete disk/config file)
        """

        self.__get_conn()
        return self.conn.undefine(vmid)

    def status(self, vmid):
        """
        Return a state suitable for server consumption.
        Aka, codes.py values, not XM output.
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


# https://libvirt.org/guide/html/Application_Development_Guide-Guest_Domains-Lifecycle.html
class VirtDomainStateMachine(Virt):

    def __init__(self, module):
        super(VirtDomainStateMachine, self).__init__(module)
        self._guest = module.params.get('name')
        self._xml = module.params.get('xml')
        self._autostart = module.params.get('autostart')
        self._result = dict(
            changed=False,
            virt=dict()
        )

    def result(self):
        self._result['virt']['node'] = super(
            VirtDomainStateMachine,
            self
        ).nodeinfo()

        self._result['virt']['domains'] = super(
            VirtDomainStateMachine,
            self
        ).info()

        return self._result

    def status(self):
        """
        Facilitator to call status method from parent class
        """

        return super(VirtDomainStateMachine, self).status(self._guest)

    def waitfor_status(self, status="running", timeout=VIRT_TIMEOUT):
        """
            Wait for status
        """
        for count in range(0, timeout):
            time.sleep(1)
            if self.status() == status:
                return True

        raise TransitionTimeoutError(
            (
                """State didn't transition to {status} after {timeout}s"""
            ).format(
                status=status,
                timeout=timeout
            )
        )

    def destroyed(self):
        """ Alias to ensure compatibility with previous version
        """

        return self.poweredoff()

    def shutdown(self):
        """
        running -> shutdown (gracefully)
        """

        if self.status() == "shutdown":
            pass
        elif self.status() == "running":
            super(VirtDomainStateMachine, self).shutdown(self._guest)
            self._result['changed'] = self.waitfor_status("shutdown")

        else:
            raise VirtDomainStateMachineError(
                (
                    """Domain {domain} must be running,"""
                    """before being shutdown."""
                    """The current domain's state is {state}."""
                ).format(
                    domain=self._guest,
                    state=self.status()
                )
            )

        return self

    def poweroff(self):
        """
        running -> shutdown (non-gracefully)
        """

        if self.status() == "shutdown":
            pass
        elif self.status() == "running":
            super(VirtDomainStateMachine, self).destroy(self._guest)
            self._result['changed'] = self.waitfor_status("shutdown")
        else:
            raise VirtDomainStateMachineError(
                (
                    """Domain {domain} must be running, """
                    """before being poweredoff."""
                    """The current domain's state is {state}."""
                ).format(
                    domain=self._guest,
                    state=self.status()
                )
            )

        return self

    def start(self):
        """
        shutdown -> running
        """

        if self.status() == "running":
            pass
        elif self.status() == "shutdown":
            super(VirtDomainStateMachine, self).start(self._guest)
            self._result['changed'] = self.waitfor_status("running")
        else:
            raise VirtDomainStateMachineError(
                (
                    """Domain {domain} must be shutdown, """
                    """before being started."""
                    """The current domain's state is {state}."""
                ).format(
                    domain=self._guest,
                    state=self.status()
                )
            )

        return self

    def autostart(self):
        """
        autostart option when needed
        """

        # Change autostart flag only if needed
        if super(VirtDomainStateMachine, self).autostart(
            self._guest,
            self._autostart
        ):
            self._result['changed'] = True

        return self

    def pause(self):
        """
        running -> paused
        """

        if self.status() == "paused":
            pass
        elif self.status() == "running":
            super(VirtDomainStateMachine, self).pause(self._guest)
            self._result['changed'] = self.waitfor_status("paused")
        else:
            raise VirtDomainStateMachineError(
                (
                    """Domain {domain} must be running, """
                    """before being paused."""
                    """The current domain's state is {state}"""
                ).format(
                    domain=self._guest,
                    state=self.status(self._guest)
                )
            )

        return self

    def unpause(self):
        """ paused -> running
        """

        if self.status() == "running":
            pass
        if self.status() == "paused":
            super(VirtDomainStateMachine, self).unpause(self._guest)
            self._result['changed'] = self.waitfor_status("running")
        else:
            raise VirtDomainStateMachineError(
                (
                    """Domain {domain} must be paused, """
                    """before being unpaused."""
                    """The current domain's state is {state}"""
                ).format(
                    domain=self._guest,
                    state=self.status()
                )
            )

        return self

    def undefine(self):
        """
        running -> transient (ephemeral)
        shutdown -> undefined
        """

        if self.status() == "undefined":
            pass
        elif (
                self.status() == "running"
                or self.status() == "shutdown"
        ):
            super(VirtDomainStateMachine, self).undefine(self._guest)
            self._result['changed'] = self.waitfor_status("undefined")
        else:
            raise VirtDomainStateMachineError(
                (
                    """Domain {domain} must be shutdown or running, """
                    """before being undefined."""
                    """The current domain's state is {state}."""
                ).format(
                    domain=self._guest,
                    state=self.status()
                )
            )

        return self

    def define(self):
        """ undefine shutdown machine
        """

        if self.status() != "undefined":
            pass
        elif self.status() == "undefined":
            if not self._xml:
                raise VirtDomainStateMachineError(
                    (
                        """Missing domain's spec (xml)"""
                        """Check if you provided xml argument"""
                    ).format(
                        domain=self._guest,
                        state=self.status()
                    )
                )

            super(VirtDomainStateMachine, self).define(self._xml)
            self._result['changed'] = self.waitfor_status("shutdown")

        return self

    def paused(self):
        """ Alias of state to action
        """

        return self.pause()

    def absent(self):
        """ Ensure absent state:
            any -> poweroff (ensure) -> undefine
        """

        try:
            self.poweroff()
        # Ignore exception related to machine not being in running state
        except VirtDomainStateMachineError:
            pass
        # Ignore exception related to machine not transitioning to shutdown
        # This scenario happens when trying to poweroff transitient domains
        except TransitionTimeoutError:
            pass

        return self.undefine()

    def present(self):
        """ Ensure present state
        """

        return self.define().autostart()

    def poweredoff(self):
        """ Ensure poweredoff state
        """

        return self.poweroff()

    def stopped(self):
        """ Ensure stopped state
        """

        try:
            self.shutdown()
        # Unplug virtual power-cable if didn't shutdown gracefully
        except TransitionTimeoutError:
            self.poweredoff()

        return self

    def running(self):
        """ Ensure running state
        """

        try:
            self.unpause()
        except VirtDomainStateMachineError:
            self.start()

        return self
