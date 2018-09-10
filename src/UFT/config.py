#!/usr/bin/env python
# encoding: utf-8
"""Description: Configuration for UFT program.
"""

__version__ = "0.1"
__author__ = "@fanmuzhi, @boqiling"

import sys, os
import ConfigParser
import ast

# station settings
STATION_CONFIG = "./xml/station.cfg"
if not os.path.exists(STATION_CONFIG):
    raise Exception("Station config does not exist!")

config = ConfigParser.RawConfigParser()
config.read(STATION_CONFIG)

DIAMOND4_LIST = ast.literal_eval(config.get('StationConfig', 'DIAMOND4_LIST'))

Mode4in1_PN = ast.literal_eval(config.get('StationConfig', 'Mode4in1_PN'))

OVERRIDE = config.getboolean('StationConfig', 'OVERRIDE')

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

ERIE_NO1 = config.get('StationConfig', 'ERIE_NO1')
ERIE_NO2 = config.get('StationConfig', 'ERIE_NO2')
ERIE_NO3 = config.get('StationConfig', 'ERIE_NO3')
ERIE_NO4 = config.get('StationConfig', 'ERIE_NO4')
ERIE_DEBUG_INFOR = config.getboolean('StationConfig', 'ERIE_DEBUG_INFOR')

ERIE_RES_CONF_NO1 = ast.literal_eval(config.get('StationConfig', 'ERIE_RES_CONF_NO1'))
ERIE_RES_CONF_NO2 = ast.literal_eval(config.get('StationConfig', 'ERIE_RES_CONF_NO2'))
ERIE_RES_CONF_NO3 = ast.literal_eval(config.get('StationConfig', 'ERIE_RES_CONF_NO3'))
ERIE_RES_CONF_NO4 = ast.literal_eval(config.get('StationConfig', 'ERIE_RES_CONF_NO4'))

SD_COUNTER = config.getint('StationConfig', 'SD_COUNTER')

CYCLE_MODE = config.getboolean('StationConfig', 'CYCLE_MODE')
CYCLE_TIMES = config.getint('StationConfig', 'CYCLE_TIMES')
CYCLE_INTERVAL = config.getint('StationConfig', 'CYCLE_INTERVAL')

HOLD_EN = config.getboolean('StationConfig', 'HOLD_EN')
HOLD_TIME = config.getint('StationConfig', 'HOLD_TIME')

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
