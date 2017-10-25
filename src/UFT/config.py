#!/usr/bin/env python
# encoding: utf-8
"""Description: Configuration for UFT program.
"""

__version__ = "0.1"
__author__ = "@fanmuzhi, @boqiling"

import sys
import ConfigParser

# station settings
STATION_CONFIG = "./xml/station.cfg"

config = ConfigParser.RawConfigParser()
config.read(STATION_CONFIG)

DIAMOND4_LIST = config.get('StationConfig', 'DIAMOND4_LIST')

Mode4in1_PN = config.get('StationConfig', 'Mode4in1_PN')

TOTAL_SLOTNUM = config.getint('StationConfig', 'TOTAL_SLOTNUM')

INTERVAL = config.getfloat('StationConfig', 'INTERVAL')

START_VOLT = config.getfloat('StationConfig', 'START_VOLT')

PS_ADDR = config.getint('StationConfig', 'PS_ADDR')
PS_CHAN = config.getint('StationConfig', 'PS_CHAN')
PS_VOLT = config.getfloat('StationConfig', 'PS_VOLT')
PS_OVP = config.getfloat('StationConfig', 'PS_OVP')
PS_CURR = config.getfloat('StationConfig', 'PS_CURR')
PS_OCP = config.getfloat('StationConfig', 'PS_OCP')

ADK_PORT = config.getint('StationConfig', 'ADK_PORT')

LD_PORT = config.get('StationConfig', 'LD_PORT')
LD_DELAY = config.getint('StationConfig', 'LD_DELAY')

ERIE_PORT = config.get('StationConfig', 'ERIE_PORT')

SD_COUNTER = config.getint('StationConfig', 'SD_COUNTER')

# database settings
# database for dut test result
# RESULT_DB = "sqlite:////home/qibo/pyprojects/UFT/test/pgem.db"
# RESULT_DB = "sqlite:///C:\\UFT\\db\\pgem.db"

if hasattr(sys, "frozen"):
    RESULT_DB = "./db/pgem.db"
else:
    RESULT_DB = "C:\\UFT\\db\\pgem.db"
# database for dut configuration
# CONFIG_DB = "sqlite:////home/qibo/pyprojects/UFT/test/pgem_config.db"
# CONFIG_DB = "sqlite:///C:\\UFT\\db\\pgem_config.db"

if hasattr(sys, "frozen"):
    CONFIG_DB = "./db/pgem_config.db"
else:
    CONFIG_DB = "C:\\UFT\\db\\pgem_config.db"

# Location to save xml log
if hasattr(sys, "frozen"):
    RESULT_LOG = "./logs/"
else:
    RESULT_LOG = "C:\\UFT\\logs\\"

# Configuration files to synchronize
if hasattr(sys, "frozen"):
    CONFIG_FILE = "./xml/"
else:
    CONFIG_FILE = "C:\\UFT\\xml\\"

# Resource Folder, include images, icons
if hasattr(sys, "frozen"):
    RESOURCE = "./res/"
else:
    RESOURCE = "C:\\UFT\\res\\"
