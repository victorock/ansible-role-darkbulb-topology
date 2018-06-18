# Copyright (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleError
from ansible.module_utils.xml import to_xml, from_xml

try:
    import libvirt
except:
    raise AnsibleError('module_utils.virt requires libvirt library. Try: pip install libvirt')


VIRT_STATE_NAME_MAP = {
    libvirt.VIR_DOMAIN_RUNNING: "running",
    libvirt.VIR_DOMAIN_BLOCKED: "idle",
    libvirt.VIR_DOMAIN_PAUSED: "paused",
    libvirt.VIR_DOMAIN_SHUTDOWN: "shutdown",
    libvirt.VIR_DOMAIN_SHUTOFF: "shutdown",
    libvirt.VIR_DOMAIN_CRASHED: "crashed",
    libvirt.VIR_DOMAIN_NOSTATE: "nostate",
}


class VirtConnectError(libvirt.libvirtError):

        def __init__(self):
            super(virtConnectError, self).__init__()
            self.msg        = self.get_error_message()
            self.code       = self.get_error_code()
            self.log()

        def log(self):
            # TODO: LOG
            pass


class VirtDomainError(libvirt.libvirtError):

        def __init__(self, log_data):
            super(virtDomainError, self).__init__()
            self.msg        = self.get_error_message()
            self.code       = self.get_error_code()
            self.log_data   = log_data
            self.log()

        def log(self):
            #TODO: Logging
            pass


class LookupError(VirtDomainError):

    def __init__(self, log_data):
        super(LookupError, self).__init__(log_data)

class WaitforStateError(VirtDomainError):

    def __init__(self, log):
        super(WaitforStateError, self).__init__(log_data)

class XMLParserError(VirtDomainError):

    def __init__(self, msg):
        super(JXMLParserError, self).__init__()
        self.msg        = msg
        self.log()

    def log(self):
        #TODO: LOG
        pass

class VirtDomainHardwareError(Exception):
    pass


# TODO: Hardware spec
class VirtDomainHardware():
    def __init__(self, model='generic', cpu=2, memory=1024, disk=60):
        self._cpu = cpu
        self._memory = memory
        self._disk = disk

        return self.config(model)

    def config(self, model):
        try:
            return getattr(self, model)()

        except AttributeError:
            raise VirtDomainHardwareError(
                (
                    "Unsupported model: {model}"
                ).format(
                    model=self._model
                )
            )

    # TODO: Generic: Hardware spec
    def generic(self):
        pass

class VirtDomainHardwareMemory(object):

    def __init__(
        self,
        size=2048,
        unit='MiB'
    ):
        self._size = size
        self._unit = unit

        return self.config()

    @property
    def size(self):
        return { '$': self._size }

    @property
    def unit(self):
        return { '@unit': self._unit }

    def config(self):
        return {
            'memory': {
                self.size,
                self.unit
            }
        }


class VirtDomainHardwareResource(object):
    def __init__(
        self,
        partition='default'
    ):
        self._partition = partition

        return self.config()

    @property
    def partition(self):
        return {
            'partition': self._partition
        }

    def config(self):
        return {
            'resource': {
                self.partition
            }
        }


class VirtDomainHardwareVcpu(object):

    def __init__(
        self,
        vcpu=2,
        placement='auto'
    ):
        self._vpcu = vcpu
        self._placement = placement

        return self.config()

    @property
    def vcpu(self):
        pass

    @property
    def placement(self):
        pass

    def config(self):
        pass

# TODO: Device spec
class VirtDomainHardwareDevice(object):
    def __init__(self):
        return self

    @property
    def address(self):
        pass

    def config(self):
        pass


# TODO: Controller spec
class VirtDomainHardwareDeviceController(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceController, self).__init__()
        return self


# TODO: Interface spec
class VirtDomainHardwareDeviceInterface(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceNetwork, self).__init__()
        return self


# TODO: Disk spec
class VirtDomainHardwareDeviceDisk(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceDisk, self).__init__()
        return self


# TODO: Video spec
class VirtDomainHardwareDeviceVideo(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceVideo, self).__init__()
        return self


# TODO: Graphic spec
class VirtDomainHardwareDeviceGraphic(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceGraphic, self).__init__()
        return self


# TODO: Controller spec
class VirtDomainHardwareDeviceInput(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceInput, self).__init__()
        return self


# TODO: Keyboard spec
class VirtDomainHardwareDeviceInputKeyboard(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceInputKeyboard, self).__init__()
        return self


# TODO: Mouse spec
class VirtDomainHardwareDeviceInputMouse(VirtDomainHardwareDevice):
    def __init__(self):
        super(VirtDomainDeviceInputMouse, self).__init__()
        return self


class VirtConnect():
    def __init__(self, uri):
        self._uri   = uri
        self._conn  = None

        return self.__enter__()

    def __enter__(self):
        return self.connect()

    def __exit__(self, etype, evalue, traceback):
        return self.disconnect()

    def connect(self):
        try:
            self._conn = libvirt.open(self._uri)

        except libvirt.libvirtError:
            raise VirtConnectError()

        else:
            return self._conn

    def disconnect(self):
        try:
            if self._conn.isAlive():
                self._conn.close()

        except libvirt.libvirtError:
            raise VirtConnectError()

        else:
            return self._conn


class VirtDomain(VirtConnect):

    def __init__(
        self,
        uri,
        spec,
        format="xml"
    ):
        super(VirtDomain, self).__init__(uri)
        self._format = format
        self._jxml = self.parse(spec)
        self._result = {}

    def parse(self, spec):
        if self._format == "xml":
            return from_xml(spec)

        elif self._format == "jxml":
            return spec

        else:
            raise VirtDomainError(
                (
                    "Invalid Format: {format}"
                ).format(
                    format=self._format
                )
            )

    def done(self):
        self._result['state'] = self.state()
        return self._result

    def domain(self):
        try:
            domain_name = self._jxml['domain']['name']
            return self._conn.lookupByName(domain_name)

        except libvirt.libvirtError:
            raise LookupError(
                (
                    "Domain {domain} does not exists"
                ).format(
                    domain=domain_name
                )
            )

        except AttributeError:
            raise AnsibleError(
                (
                    "Invalid spec: {spec}"
                ).format(
                    spec=self._jxml
                )
            )

    def state(self):
        try:
            domain_state = self.domain().info()[0]
            return VIRT_STATE_NAME_MAP.get(domain_state)

        except (AttributeError, LookupError):
            return VIRT_STATE_NAME_MAP.get(libvirt.VIR_DOMAIN_NOSTATE)

    def waitfor_state(self, state, waitfor=1):
        for wait in range(waitfor):
            time.sleep(1)
            if self.state() == state:
                return self.state()

        raise WaitforStateError(
            (
                "state is not {state} after {waitfor}"
            ).format(
                state=state,
                waitfor=waitfor
            )
        )

    def define(self):
        try:
            self.domain()

        except LookupError:
            xml_domain_spec = to_xml(self._jxml)
            self._conn.defineXML(xml_domain_spec)
            self.waitfor_state("shutdown", 40)
            self._result['changed'] = True
            self._result['virtdomain'] = (
                "Domain {domain} defined"
            ).format(
                domain=self._jxml['domain']['name']
            )

        else:
            self._result['changed'] = False
            self._result['virtdomain'] = (
                "Domain {domain} already defined"
            ).format(
                domain=self._jxml['domain']['name']
            )

        finally:
            return self.done()

    def undefine(self):
        try:
            self.waitfor_state("nostate")

        except WaitforStateError:
            self.poweroff()
            self.domain().undefine()
            self.waitfor_state("nostate", 30)
            self._result['changed'] = True
            self._result['virtdomain'] = (
                "Domain {domain} undefined"
            ).format(
                domain=self._jxml['domain']['name']
            )

        else:
            self._result['changed'] = False
            self._result['virtdomain'] = (
                "Domain {domain} already undefined"
            ).format(
                domain=self._jxml['domain']['name']
            )

        finally:
            return self.done()

    def start(self):
        try:
            self.waitfor_state("running")

        except WaitforStateError:
            self.domain().create()
            self.waitfor_state("running", 40)
            self._result['changed'] = True
            self._result['virtdomain'] = (
                "Domain {domain} running"
            ).format(
                domain=self._jxml['domain']['name']
            )

        else:
            self._result['changed'] = False
            self._result['virtdomain'] = (
                "Domain {domain} already running"
            ).format(
                domain=self._jxml['domain']['name']
            )

        finally:
            return self.done()

    def shutdown(self):
        try:
            self.waitfor_state("shutdown")

        except WaitforStateError:
            self.domain().shutdown()
            self.waitfor_state("shutdown", 40)
            self._result['changed'] = True
            self._result['virtdomain'] = (
                "Domain {domain} shutdown"
            ).format(
                domain=self._jxml['domain']['name']
            )

        else:
            self._result['changed'] = False
            self._result['virtdomain'] = (
                "Domain {domain} already shutdown"
            ).format(
                domain=self._jxml['domain']['name']
            )

        finally:
            return self.done()

    def poweroff(self):
        try:
            self.waitfor_state("shutdown")

        except WaitforStateError:
            self.domain().destroy()
            self.waitfor_state("shutdown", 40)
            self._result['changed'] = True
            self._result['virtdomain'] = (
                "Domain {domain} shutdown"
            ).format(
                domain=self._jxml['domain']['name']
            )

        else:
            self._result['changed'] = False
            self._result['virtdomain'] = (
                "Domain {domain} already shutdown"
            ).format(
                domain=self._jxml['domain']['name']
            )

        finally:
            return self.done()

    def pause(self):
        try:
            self.waitfor_state("paused")

        except WaitforStateError:
            self.domain().suspend()
            self.waitfor_state("paused", 40)
            self._result['changed'] = True
            self._result['virtdomain'] = (
                "Domain {domain} paused"
            ).format(
                domain=self._jxml['domain']['name']
            )

        else:
            self._result['changed'] = False
            self._result['virtdomain'] = (
                "Domain {domain} already paused"
            ).format(
                domain=self._jxml['domain']['name']
            )

        finally:
            return self.done()

    def unpause(self):
        try:
            self.waitfor_state("running")

        except WaitforStateError:
            self.domain().resume()
            self.waitfor_state("running", 20)
            self._result['changed'] = True
            self._result['virtdomain'] = (
                "Domain {domain} shutdown"
            ).format(
                domain=self._jxml['domain']['name']
            )

        else:
            self._result['changed'] = False
            self._result['virtdomain'] = (
                "Domain {domain} already shutdown"
            ).format(
                domain=self._jxml['domain']['name']
            )

        finally:
            return self.done()
