#!/usr/bin/env python
#
#  Written by: Andrey Skvortsov <andrej.skvortzov@gmail.com>
#
# - License --------------------------------------------------------------
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 3
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# - Change Log -----------------------------------------------------------
#

import usb

import sys
import getopt
import logging


GET_REPORT = 0x01
SET_REPORT = 0x09

HID_REQ_TO_HOST = 0xA1
HID_REQ_TO_DEV  = 0x21

REPORT_TYPE_INPUT   = 0x100
REPORT_TYPE_OUTPUT  = 0x200
REPORT_TYPE_FEATURE = 0x300

log = logging.getLogger('mp709')

class relayState:
  off = 0
  on  = 1
  noChange = 3
  toggle = 4


class mp709:

  GET_INFO     = (0x1D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)
  SET_PORT_ON  = (0xE7, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)
  SET_PORT_OFF = (0xE7, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00)
  GET_PORT     = (0x7E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)

  REPORT_LEN   = 8

  def __init__(self, device, id):
    self.handle = None

    if (device.idVendor != 0x16C0) or (device.idProduct != 0x05DF):
      raise ValueError()

    conf = device.configurations[0]
    self.dev = device
    self.intf = conf.interfaces[0][0]
    self.intfNum = self.intf.interfaceNumber

    self.open()
    if id != 0:
      info = self.getInfo()
      if info['id'] != id:
        self.close()
        raise ValueError()

  def __del__(self):
    if self.handle:
      self.close()

  def __str__(self):
    if self.handle:
      info = self.getInfo()
      str = " "
      str = str + "family (%d), " % info['family']
      str = str + "fw version (%d), " % info ['version']
      str = str + "id (%d), " % info['id']

      str = str + "state (%d)" % self.getPort()
    else:
      str = "No MP709 device"
    return str

  def open(self):
    if self.handle:
      self.close()

    self.handle = self.dev.open()
    try:
      self.handle.detachKernelDriver(self.intf)      
    except:
      pass
    
    self.handle.setConfiguration(self.dev.configurations[0])
    self.handle.claimInterface(self.intf)
    self.handle.setAltInterface(self.intf)

  def close(self):
    if self.handle:
      self.handle.releaseInterface()

    self.handle = None
    self.dev = None
    self.intf = None



  def setPort(self, state, timeout = 100):
    if state:
      buffer = self.SET_PORT_ON
    else:
      buffer = self.SET_PORT_OFF
    return self.handle.controlMsg(requestType = HID_REQ_TO_DEV,
                                  request     = SET_REPORT,
                                  buffer      = buffer,
                                  value       = REPORT_TYPE_FEATURE,
                                  index       = self.intfNum,
                                  timeout     = timeout)

  def getPort(self, timeout = 100):
    self.handle.controlMsg(requestType = HID_REQ_TO_DEV,
                           request     = SET_REPORT,
                           buffer      = self.GET_PORT,
                           value       = REPORT_TYPE_FEATURE,
                           index       = self.intfNum,
                           timeout     = timeout)

    buffer = self.handle.controlMsg(requestType = HID_REQ_TO_HOST,
                           request     = GET_REPORT,
                           buffer      = self.REPORT_LEN,
                           value       = REPORT_TYPE_FEATURE,
                           index       = self.intfNum,
                           timeout     = timeout)

    portOn  = 0x00;
    portOff = 0x19;
    return (buffer[1] == buffer[2]) and (buffer[1] == portOn)

  def getInfo(self, timeout = 100):
    self.handle.controlMsg(requestType = HID_REQ_TO_DEV,
                           request     = SET_REPORT,
                           buffer      = self.GET_INFO,
                           value       = REPORT_TYPE_FEATURE,
                           index       = self.intfNum,
                           timeout     = timeout)

    buffer = self.handle.controlMsg(requestType = HID_REQ_TO_HOST,
                                    request     = GET_REPORT,
                                    buffer      = self.REPORT_LEN,
                                    value       = REPORT_TYPE_FEATURE,
                                    index       = self.intfNum,
                                    timeout     = timeout)

    family  = buffer[1]
    version = buffer[2] + buffer[3]*(1<<8);
    id      = buffer[7] + buffer[6]*(1<<8) + buffer[5]*(1<<16) + buffer[4]*(1<<24);

    return {'family': family, 'version': version, 'id': id}


class relaysControl:
  def __init__(self):
    self.state = relayState.noChange
    self.id = 0

  def enumerateRelays(self):
    busses = usb.busses()
    relays = []
    for bus in busses:
      devices = bus.devices
      for dev in devices:
        try:
          relay = mp709(dev, self.id)
        except ValueError:
          pass
        else:
          relays.append(relay)
    if len(relays) == 0:
      log.info("No relay found")
      raise RuntimeWarning
    return relays

  def setState(self, state_in):
    states = {'on':       relayState.on,
              'off':      relayState.off,
              'noChange': relayState.noChange,
              'toggle':   relayState.toggle};
    try:
      state = states[state_in];
    except KeyError as e:
      log.error("Unsupported state, %s" % e)
      raise
    else:
      self.state = state

  def setId(self, id):
    self.id = int(id)

  def controlRelays(self, relays):
    for r in relays:
      if self.state in (relayState.on, relayState.off):
        r.setPort(self.state == relayState.on)
      elif self.state == relayState.toggle:
        r.setPort( not r.getPort() )

      log.info(r)

  def main(self):
    try:
      relays = self.enumerateRelays()
      self.controlRelays(relays)
    except:
      raise




def usage():
  print("Usage: mp709.py [--state 0] [--id 3758]")
  print("  -h | --help    : print this help")
  print("  -V | --version : version")
  print("  -s | --state   : control state of the relay. Possible values are: ")
  print("                   on, off, noChange, toggle")
  print("                   Default value is noChange.")
  print("  -i | --id      : control only relay with certain id. ")
  print("                   0 means control all relays. By default is 0")
  print("  -v | --verbose : increase verbosity")
  sys.exit(2)
  

def version():
  print("mp709.py, v. 1.0 2015/05/30 Andrey Skvortsov")
  sys.exit(0)
  

def main(argv):
  control = relaysControl()
  logging.basicConfig(level = logging.NOTSET)  
  verbose = 30
  
  try:
    opts, args = getopt.getopt(argv,
                               "hVs:i:v",
                               ["help", "version", "state", "id", "verbose"])
  except getopt.GetoptError as e:
    log.error("Unknown option:", e)

    usage()
    
  try:
    if opts:
      for o, a in opts:
        if o in ("-h", "--help"):
          usage()
        elif o in ("-V", "--version"):
          version()
        elif o in ("-s", "--state"):
          control.setState(a)
        elif o in ("-i", "--id"):
          control.setId(a)
        elif o in ("-v", "--verbose"):
          verbose = max(0, verbose - 10)

    log.setLevel(verbose)
    control.main()
  except SystemExit as e:
    raise
  except:
    log.error("Failed")
    sys.exit(3)

if __name__=="__main__":
  main(sys.argv[1:])
