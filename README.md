Ansible Darkbulb Topology
=========

Simple Role to Deploy Darkbulb Network.

Requirements
------------

None

Role Variables
--------------

None

Dependencies
------------

None

Example Playbook
----------------

```YAML
- name: "Deploy Ansible Tower by Red Hat"
  hosts: darkbulb
  become: true

  roles:
    - victorock.darkbulb-topology
```

License
-------

GPLv3

Author Information
------------------

Victor da Costa
