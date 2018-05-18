# (c) 2018, Victor da Costa <victorockeiro@gmail.com>
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

from xmltodict import unparse as XMLDecoder
from xmltodict import parse as XMLEncoder
from ansible.plugins.filter.core import to_json
from ansible.module_utils._text import to_text

def to_xml(data=dict(), *args, **kw):
    '''Convert JSON to XML'''
    xml_data = XMLDecoder(  data,
                            pretty=kw.get('pretty', False),
                            attr_prefix=kw.get('attr_prefix', '@'),
                            cdata_key=kw.get('cdata_key', '$') )

    return to_text( xml_data,
                    errors='surrogate_or_strict',
                    nonstring='simplerepr' )

def from_xml(data='', *args, **kw):
    '''Convert XML to JSON'''
    ordered_dict_data = XMLEncoder( data,
                                    process_namespaces=kw.get('process_namespaces', True),
                                    attr_prefix=kw.get('attr_prefix', '@'),
                                    cdata_key=kw.get('cdata_key', '$') )

    return to_json( ordered_dict_data )

class FilterModule(object):
    """Filters for libvirt"""

    filter_map = {
        'to_xml': to_xml,
        'from_xml': from_xml
    }

    def filters(self):
        return self.filter_map
