Ansible Topology Builder
=========

Ansible Role to Build Network Topologies

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
    - victorock.network_topology_builder
```

License
-------

GPLv3

Author Information
------------------

Victor da Costa
