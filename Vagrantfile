# frozen_string_literal: true
require 'yaml'
lab = YAML.safe_load(File.read(File.join(__dir__, 'lab.yml')))

Vagrant.configure('2') do |config|
  config.vm.box = ENV.fetch('LAB_BOX', 'bento/ubuntu-24.04')
  config.vm.box_check_update = false
  config.vm.synced_folder '.', '/vagrant', disabled: true
  config.ssh.insert_key = true
  config.vm.boot_timeout = 600

  lab.fetch('lab_nodes').each do |name, node|
    config.vm.define name do |vm|
      vm.vm.hostname = "#{name}.#{lab.fetch('lab_domain')}"
      vm.vm.provider :virtualbox do |vb|
        vb.name = "network-infra-#{name}"
        vb.memory = node.fetch('memory')
        vb.cpus = node.fetch('cpus')
        vb.customize ['modifyvm', :id, '--macaddress1', node.fetch('mgmt_mac').delete(':')]
      end
      vm.vm.provider :libvirt do |lv|
        lv.memory = node.fetch('memory')
        lv.cpus = node.fetch('cpus')
        lv.management_network_name = 'network-infra-mgmt'
        lv.management_network_address = '172.29.240.0/24'
        lv.management_network_mac = node.fetch('mgmt_mac')
      end
      %w[dmz lan].each do |segment|
        next unless node.key?("#{segment}_mac")
        address = if name == 'router'
                    lab.fetch("lab_router_#{segment}")
                  elsif name == 'server'
                    lab.fetch('lab_server_ip')
                  else
                    lab.fetch('lab_client_ip')
                  end
        vm.vm.network :private_network, ip: address, auto_config: false,
          mac: node.fetch("#{segment}_mac").delete(':'),
          virtualbox__intnet: "network-infra-#{segment}",
          libvirt__network_name: "network-infra-#{segment}",
          libvirt__mac: node.fetch("#{segment}_mac"),
          libvirt__dhcp_enabled: false, libvirt__forward_mode: 'veryisolated',
          libvirt__host_ip: address.sub(/\d+$/, '254')
      end
      if name == 'router'
        vm.vm.network :forwarded_port, guest: 8080, host: 8080,
          host_ip: '127.0.0.1', auto_correct: false
      end
    end
  end
end
