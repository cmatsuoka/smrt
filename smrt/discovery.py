#!/usr/bin/env python

import sys, socket, random, logging, platform, argparse

import netifaces

from . import IncompatiblePlatformException
from .protocol import *
from .network import *

DISCOVERY_TIMEOUT = 0.5

logger = logging.getLogger(__name__)

def discover_switches(interfaces='all'):
    if interfaces == 'all':
        interfaces = netifaces.interfaces()
    settings = []
    for iface in interfaces:
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET not in addrs: continue
        if netifaces.AF_LINK not in addrs: continue
        assert len(addrs[netifaces.AF_LINK]) == 1
        mac = addrs[netifaces.AF_LINK][0]['addr']
        for addr in addrs[netifaces.AF_INET]:
            if 'broadcast' not in addr or 'addr' not in addr: continue
            settings.append((iface, addr['addr'], mac, addr['broadcast']))

    for iface, ip, mac, broadcast in settings:
        logger.warning((iface, ip, mac, broadcast))
        sequence_id = random.randint(0, 1000)
        header = DEFAULT_HEADER.copy()
        header.update({
          'sequence_id': sequence_id,
          'host_mac': bytes(int(byte, 16) for byte in mac.split(':')),
        })
        packet = assemble_packet(header, {})
        packet = encode(packet)

        if platform.system().lower() == 'darwin':
            rs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            rs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            rs.bind(('', UDP_RECEIVE_FROM_PORT))
            rs.settimeout(DISCOVERY_TIMEOUT)
        elif platform.system().lower() == 'linux':
            rs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            rs.bind((BROADCAST_ADDR, UDP_RECEIVE_FROM_PORT))
            #rs.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            rs.settimeout(DISCOVERY_TIMEOUT)
        else:
            raise IncompatiblePlatformException()

        ss = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ss.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        ss.bind((ip, UDP_RECEIVE_FROM_PORT))
        ss.sendto(packet, (BROADCAST_ADDR, UDP_SEND_TO_PORT))
        ss.close()



        while True:
            try:
                data, addr = rs.recvfrom(1500)
            except:
                break
            data = decode(data)
            header, payload = split(data)
            payload = interpret_payload(payload)
            context = {'iface': iface, 'ip': ip, 'mac': mac, 'broadcast': broadcast}
            yield context, header, payload
        rs.close()

def main():
    if platform.system().lower() not in ('darwin', 'linux'):
        sys.stderr.write('Discovery is not implemented for the platform %s' % platform.system())
        sys.exit(4)
    parser = argparse.ArgumentParser()
    parser.add_argument('interfaces', metavar='INTERFACE', nargs='*', default='all')
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    switches = discover_switches(interfaces=args.interfaces)
    for context, header, payload in switches:
        get = lambda kind: get_payload_item_value(payload, kind)
        fmt =  "Found a switch:  Host:   (Interface: {iface:8s} IP: {host_ip}  Broadcast: {broadcast})\n"
        fmt += "                 Switch: (Kind: {kind:12s}  MAC Address: {mac}   IP Address: {switch_ip})"
        print(fmt.format(iface=context['iface'], host_ip=context['ip'], broadcast=context['broadcast'],
                         kind=get('type'), mac=get('mac'), switch_ip=get('ip_addr')))

if __name__ == "__main__": main()
