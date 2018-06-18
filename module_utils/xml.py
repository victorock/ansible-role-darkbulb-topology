# (c) 2018, Victor da Costa <@victorock>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import json
from ansible.module_utils._text import to_text
from ansible.errors import AnsibleError

try:
    from xmltodict import unparse as XMLEncoder
    from xmltodict import parse as XMLDecoder
except:
    raise AnsibleError('module_utils.xml requires xmltodict library. Try: pip install xmltodict')


def to_xml(data, *args, **kw):
    '''Convert JSON to XML'''
    xml_data = XMLEncoder(data,
                        pretty=kw.get('pretty', False),
                        attr_prefix=kw.get('attr_prefix', '@'),
                        cdata_key=kw.get('cdata_key', '$'))

    return to_text(xml_data,
                errors='surrogate_or_strict',
                nonstring='simplerepr')


def from_xml(data, *args, **kw):
    '''Convert XML to JSON'''
    ordered_dict_data = XMLDecoder(data,
                                process_namespaces=kw.get('process_namespaces', True),
                                attr_prefix=kw.get('attr_prefix', '@'),
                                cdata_key=kw.get('cdata_key', '$'))

    return json.dumps(ordered_dict_data)
