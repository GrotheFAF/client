"""
Created on Mar 22, 2012

@author: thygrrr
"""
import logging
import sys
import platform
logger = logging.getLogger(__name__)

UPNP_APP_NAME = "Forged Alliance Forever"

# Fields in mapping_port
# UpnpPort.Description 
# UpnpPort.ExternalPort
# UpnpPort.ExternalIPAddress
# UpnpPort.InternalClient
# UpnpPort.InternalPort
# UpnpPort.Protocol
# UpnpPort.Enabled


def dump_mapping(mapping_port):
    logger.info("-> %s mapping of %s:%d to %s:%d" % (mapping_port.Protocol, mapping_port.InternalClient, 
                                                     mapping_port.InternalPort, mapping_port.ExternalIPAddress, 
                                                     mapping_port.ExternalPort))

if platform.system() == "Windows":
    def create_port_mapping(ip, port, protocol="UDP"):
        logger.info("UPnP mapping {}:{}".format(ip, port))
        try:
            import win32com.client
            natu_pnp = win32com.client.Dispatch("HNetCfg.NATUPnP")
            mapping_ports = natu_pnp.StaticPortMappingCollection

            if mapping_ports:
                mapping_ports.Add(port, protocol, port, ip, True, UPNP_APP_NAME)
                for mapping_port in mapping_ports:
                    if mapping_port.Description == UPNP_APP_NAME:
                        dump_mapping(mapping_port)
            else:
                logger.error("Couldn't get StaticPortMappingCollection")
        except:
            logger.error("Exception in UPnP create_port_mapping.",
                         exc_info=sys.exc_info())

    def remove_port_mappings():
        logger.info("Removing UPnP port mapping.")
        try:
            import win32com.client
            natu_pnp = win32com.client.Dispatch("HNetCfg.NATUPnP")
            mapping_ports = natu_pnp.StaticPortMappingCollection

            if mapping_ports:
                if mapping_ports.Count:
                    for mapping_port in mapping_ports:
                        if mapping_port.Description == UPNP_APP_NAME:
                            dump_mapping(mapping_port)
                            mapping_ports.Remove(mapping_port.ExternalPort, mapping_port.Protocol)
                else:
                    logger.info("No mappings found / collection empty.")
            else:
                logger.error("Couldn't get StaticPortMappingCollection")
        except:
            logger.error("Exception in UPnP remove_port_mappings.", exc_info=sys.exc_info())
else:
    def create_port_mapping(ip, port, protocol='UDP'):
        logger.info("FIXME: Create a UPNP mapper for platform != Windows")

    def remove_port_mappings():
        logger.info("FIXME: Create a UPNP mapper for platform != Windows")
