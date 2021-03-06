#!/usr/bin/env python
# encoding: utf-8
"""Description: pgem parallel test on UFT test fixture.
Currently supports 4 duts in parallel.
"""

__version__ = "0.1"
__author__ = "@fanmuzhi, @boqiling"
__all__ = ["Channel", "ChannelStates"]

import sys

from UFT.devices import pwr, load, aardvark
from UFT.devices import erie
from UFT.models import DUT_STATUS, DUT, Cycle, PGEMBase, Diamond4
from UFT.backend import load_config, load_test_item, get_latest_revision
from UFT.backend.session import SessionManager
from UFT.backend import simplexml
from UFT.config import *
import threading
from Queue import Queue
import logging
import time
import os
import traceback
import datetime

logger = logging.getLogger(__name__)


class ChannelStates(object):
    EXIT = -1
    INIT = 0x0A
    LOAD_DISCHARGE = 0x0C
    CHARGE = 0x0E
    PROGRAM_VPD = 0x0F
    CHECK_CAPACITANCE = 0x1A
    CHECK_ENCRYPTED_IC = 0x1B
    CHECK_TEMP = 0x1C
    DUT_DISCHARGE = 0x1D
    CHECK_POWER_FAIL = 0x1E
    RECHARGE = 0x1F
    CHECK_VPD = 0x10
    HOLD = 0x0D


class BOARD_STATUS(object):
    Idle = 0  # wait to test
    Pass = 1  # pass the test
    Fail = 2  # fail in test
    Running = 8


class Channel(threading.Thread):
    def __init__(self, name, barcode_list, cable_barcodes_list, capacitor_barcodes_list, mode4in1, channel_id=0):
        """initialize channel
        :param name: thread name
        :param barcode_list: list of 2D barcode of dut.
        :param channel_id: channel ID, from 0 to 7
        :return: None
        """
        # channel number for mother board.
        # 8 mother boards can be stacked from 0 to 7.
        # use 1 motherboard in default.
        self.channel = channel_id

        self.channelresult = BOARD_STATUS.Idle
        self.dutnumber = 0

        # product type setting
        self.producttype=''

        # Amber 4x/e uses master port + shared port mode
        self.InMode4in1 = mode4in1

        # setup dut_list
        self.dut_list = []
        self.config_list = []
        self.barcode_list = barcode_list
        self.cable_barcodes_list = cable_barcodes_list
        self.capacitor_barcodes_list = capacitor_barcodes_list

        # progress bar, 0 to 100
        self.progressbar = 0

        # counter, to calculate charge and discharge time based on interval
        self.counter = 0

        # pre-discharge current, default to 0.8A
        self.current = 2.0

        # exit flag and queue for threading
        self.exit = False
        self.queue = Queue()
        super(Channel, self).__init__(name=name)

    def read_volt(self, dut):
        val = dut.meas_vcap()
        return val

    def init(self):
        """ hardware initialize in when work loop starts.
        :return: None.
        """
         # setup load
        #self.ld.reset()
        #time.sleep(2)

        logger.info("Initiate Hardware of Channel {0}...".format(self.channel))
        #first setup erie
        if self.channel == 0:
            self.erie = erie.Erie(port=ERIE_NO1, boardid=1)
        elif self.channel == 1:
            self.erie = erie.Erie(port=ERIE_NO2, boardid=2)
        elif self.channel == 2:
            self.erie = erie.Erie(port=ERIE_NO3, boardid=3)
        elif self.channel == 3:
            self.erie = erie.Erie(port=ERIE_NO4, boardid=4)

        # aardvark
        self.adk = aardvark.Adapter(self.erie)
        # setup load
        self.ld = load.DCLoad(self.erie)
        # setup main power supply
        self.ps = pwr.PowerSupply(self.erie)

        logger.info("mode 4in1 is {0}".format(self.InMode4in1))

        for slot in range(TOTAL_SLOTNUM):
            self.ld.select_channel(slot)
            self.ld.input_off()
            #time.sleep(1)
            #self.ld.protect_on()
            #self.ld.change_func(load.DCLoad.ModeCURR)
            #time.sleep(1)

            self.ps.selectChannel(slot)
            self.ps.deactivateOutput()

            self.erie.LedOff(slot)

        # setup power supply
        #self.ps.selectChannel(node=PS_ADDR, ch=PS_CHAN)

        setting = {"volt": PS_VOLT, "curr": PS_CURR,
                   "ovp": PS_OVP, "ocp": PS_OCP}
        #self.ps.set(setting)
        #self.ps.activateOutput()
        time.sleep(1)
        #volt = self.ps.measureVolt()
        #curr = self.ps.measureCurr()
        '''
        if not ((PS_VOLT - 1) < volt < (PS_VOLT + 1)):
            self.ps.setVolt(0.0)
            logging.error("Power Supply Voltage {0} "
                          "is not in range".format(volt))
            raise AssertionError("Power supply voltage is not in range")
        if not (curr >= 0):
            self.ps.setVolt(0.0)
            logging.error("Power Supply Current {0} "
                          "is not in range".format(volt))
            raise AssertionError("Power supply current is not in range")
        '''

        # setup dut_list
        for i, bc in enumerate(self.barcode_list):
            if bc != "":
                # dut is present
                dut = PGEMBase(device=self.adk,
                               slot=i,
                               barcode=bc)
                logger.info("dut: {0} SN is {1}"
                            .format(dut.slotnum, bc))
                if self.InMode4in1:
                    if dut.partnumber not in Mode4in1_PN:
                        raise Exception("This partnumber {0} does not support Mode4in1".format(dut.partnumber))
                else:
                    if dut.partnumber in Mode4in1_PN:
                        if not OVERRIDE:
                            raise Exception("This partnumber {0} NEED Mode4in1".format(dut.partnumber))
                dut.status = DUT_STATUS.Idle
                dut.cable_barcode = self.cable_barcodes_list[i]
                dut.capacitor_barcode = self.capacitor_barcodes_list[i]
                dut.testdate = datetime.datetime.now()
                self.dut_list.append(dut)
                dut_config = load_config("sqlite:///" + CONFIG_DB,
                                         dut.partnumber, dut.revision)
                self.config_list.append(dut_config)
                self.set_productype(dut.slotnum, dut.producttype)
                latest_revision = get_latest_revision("sqlite:///" + CONFIG_DB,
                                         dut.partnumber)
                logger.info("dut: {0} has the latest revision of this partnumber is {1}"
                            .format(dut.slotnum, latest_revision))
                if latest_revision != dut.revision:
                    if not OVERRIDE:
                        dut.errormessage = "Not the latest revision"
                        dut.status = DUT_STATUS.Fail

                self.channelresult = BOARD_STATUS.Running
                self.dutnumber += 1
            else:
                # dut is not loaded on fixture
                self.dut_list.append(None)
                self.config_list.append(None)

    def _check_hardware_ready_(self, dut):
        for i in range(5):
            if dut.read_hwready():
                return True
            time.sleep(1)
        return False

    def _turn_off_load(self, slot):
        self.ld.select_channel(slot)
        self.ld.input_off()
        if self.InMode4in1:
            for i in range(1, 4):
                self.ld.select_channel(slot + i)
                self.ld.input_off()

    def _turn_on_power(self, slot):
        self.ps.selectChannel(slot)
        self.ps.activateOutput()
        time.sleep(0.1)
        if self.InMode4in1:
            for i in range(1, 4):
                self.ps.selectChannel(slot + i)
                self.ps.activateOutput()
                time.sleep(0.1)

    def _turn_off_power(self, slot):
        self.ps.selectChannel(slot)
        self.ps.deactivateOutput()
        if self.InMode4in1:
            for i in range(1, 4):
                self.ps.selectChannel(slot + i)
                self.ps.deactivateOutput()

    def set_productype(self, port, pt):
        if pt == "AGIGA9821":
            logger.info("dut: {0} PN: {1} setting type: Pearl family".format(port, pt))
            self.erie.SetProType(port, 0x00)
            self.producttype='Pearl'
        if pt == "AGIGA9822" or pt == "AGIGA9823" or pt == "AGIGA9824":
            logger.info("dut: {0} PN: {1} setting type: Amber family ".format(port, pt))
            self.erie.SetProType(port, 0x01)
            self.producttype='Amber'
        if pt == "AGIGA9831":
            logger.info("dut: {0} PN: {1} setting type: Garnet family ".format(port, pt))
            self.erie.SetProType(port, 0x02)
            self.producttype='Garnet'
        if pt == "AGIGA9832":
            logger.info("dut: {0} PN: {1} setting type: Pearl2 family (as Amber by temporary) ".format(port, pt))
            self.erie.SetProType(port, 0x01)
            self.producttype='Amber2'
        if pt == "AGIGA9834":
            logger.info("dut: {0} PN: {1} setting type: Jamber family (as Amber by temporary) ".format(port, pt))
            self.erie.SetProType(port, 0x01)
            self.producttype='Jamber'

    def charge_dut(self):
        """charge
        """

        power_on_delay = False
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Charge")
            # print dut.slotnum
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            power_on_delay = True
            self._turn_on_power(dut.slotnum)

            # start charge
            dut.status = DUT_STATUS.Charging

        all_charged = False
        self.counter = 0
        start_time = time.time()
        if power_on_delay:
            time.sleep(5)

        while (not all_charged):
            all_charged = True
            for dut in self.dut_list:
                try:
                    if dut is None:
                        continue
                    config = load_test_item(self.config_list[dut.slotnum],
                                            "Charge")
                    if (not config["enable"]):
                        continue
                    if (config["stoponfail"]) & \
                            (dut.status != DUT_STATUS.Charging):
                        continue

                    threshold = float(config["Threshold"].strip("aAvV"))
                    ceiling = float(config["Ceiling"].strip("aAvV"))
                    max_chargetime = config["max"]
                    min_chargetime = config["min"]

                    self.switch_to_dut(dut.slotnum)
                    if not self._check_hardware_ready_(dut):
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "DUT is not ready."
                    this_cycle = Cycle()
                    this_cycle.vin = dut.meas_vin()
                    this_cycle.counter = self.counter
                    this_cycle.time = time.time()
                    temperature = dut.check_temp()
                    this_cycle.temp = temperature
                    this_cycle.state = "charge"
                    self.counter += 1

                    self.ld.select_channel(dut.slotnum)
                    this_cycle.vcap = dut.meas_vcap()
                    chargestatue = dut.charge_status()

                    charge_time = this_cycle.time - start_time
                    dut.charge_time = charge_time
                    if (temperature>50 or temperature<10):
                        all_charged &= True
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "Temperature out of range."
                    elif (charge_time > max_chargetime):
                        all_charged &= True
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "Charge Time Too Long."
                    elif (chargestatue):
                        if(ceiling > this_cycle.vcap >= threshold)&(max_chargetime>dut.charge_time>min_chargetime):  #dut.meas_chg_time()
                            all_charged &= True
                            dut.status = DUT_STATUS.Idle  # pass
                        else:
                            dut.status = DUT_STATUS.Fail
                            dut.errormessage = "Charge Time or Vcap failed"
                    else:
                        all_charged &= False
                    dut.cycles.append(this_cycle)
                    logger.info("dut: {0} status: {1} vcap: {2} "
                                "temp: {3} charged: {4} message: {5} ".
                                format(dut.slotnum, dut.status, this_cycle.vcap,
                                       this_cycle.temp, chargestatue, dut.errormessage))
                except aardvark.USBI2CAdapterException:
                    logger.info("dut: {0} IIC access failed.".
                                format(dut.slotnum))
                    all_charged &= True
                    dut.status = DUT_STATUS.Fail
                    dut.errormessage = "IIC access failed."

            if not all_charged:
                time.sleep(INTERVAL)

    def hold_power_on(self):
        """
        Hold the power on status for specified time
        :return:
        """
        logger.info("HOLD power on for {0} minutes ".format(HOLD_TIME))
        keep_hold=True
        total_seconds=HOLD_TIME*60
        start_time = time.time()
        while(keep_hold):
            time.sleep(INTERVAL)
            if (time.time() - start_time) > total_seconds:
                keep_hold=False

    def recharge_dut(self):
        """charge
        """
        power_on_delay = False
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Recharge")
            # print dut.slotnum
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            power_on_delay = True
            self._turn_on_power(dut.slotnum)

            # start charge
            dut.status = DUT_STATUS.Charging

        all_charged = False
        self.counter = 0
        start_time = time.time()

        if power_on_delay:
            time.sleep(5)

        while (not all_charged):
            all_charged = True
            for dut in self.dut_list:
                try:
                    shutdown=False
                    if dut is None:
                        continue
                    config = load_test_item(self.config_list[dut.slotnum],
                                            "Recharge")
                    if (not config["enable"]):
                        continue
                    if (config["stoponfail"]) & \
                            (dut.status != DUT_STATUS.Charging):
                        continue

                    threshold = float(config["Threshold"].strip("aAvV"))
                    ceiling = float(config["Ceiling"].strip("aAvV"))
                    max_chargetime = config["max"]
                    min_chargetime = config["min"]

                    if config.get("Shutdown",False)=="Yes":
                        shutdown=True
                    self.switch_to_dut(dut.slotnum)
                    if not self._check_hardware_ready_(dut):
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "DUT is not ready."
                    #this_cycle = Cycle()
                    #this_cycle.vin = dut.meas_vin()
                    #this_cycle.counter = self.counter
                    #this_cycle.time = time.time()
                    temperature = dut.check_temp()
                    #this_cycle.temp = temperature
                    #this_cycle.state = "charge"
                    self.counter += 1

                    self.ld.select_channel(dut.slotnum)
                    vcap = dut.meas_vcap()
                    chargestatue=dut.charge_status()

                    charge_time = time.time() - start_time
                    dut.charge_time = charge_time
                    if (temperature>50 or temperature<10):
                        all_charged &= True
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "Temperature out of range."
                    elif (charge_time > max_chargetime):
                        all_charged &= True
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "Charge Time Too Long."
                    elif (chargestatue):
                        if(ceiling > vcap >= threshold)&(max_chargetime>dut.charge_time>min_chargetime):  #dut.meas_chg_time()
                            all_charged &= True
                            self._turn_off_power(dut.slotnum)

                            if shutdown == True:
                                self.erie.ShutdownDUT(dut.slotnum)
                            dut.status = DUT_STATUS.Idle  # pass
                        else:
                            dut.status = DUT_STATUS.Fail
                            dut.errormessage = "Charge Time or Vcap failed"
                    else:
                        all_charged &= False
                    #dut.cycles.append(this_cycle)
                    logger.info("dut: {0} status: {1} vcap: {2} "
                                "temp: {3} charged: {4} message: {5} ".
                                format(dut.slotnum, dut.status, vcap,
                                       temperature, chargestatue, dut.errormessage))
                except aardvark.USBI2CAdapterException:
                    logger.info("dut: {0} IIC access failed.".
                                format(dut.slotnum))
                    all_charged &= True
                    dut.status = DUT_STATUS.Fail
                    dut.errormessage = "IIC access failed."

            if not all_charged:
                time.sleep(INTERVAL)

    def discharge_dut(self):
        """discharge
        """
        power_off_delay = False
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Discharge")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            power_off_delay = True
            self._turn_off_power(dut.slotnum)

        if power_off_delay:
            time.sleep(2)

        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Discharge")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue

            self.ld.select_channel(dut.slotnum)
            self.current = float(config["Current"].strip("aAvV"))
            self.ld.set_curr(self.current)  # set discharge current
            self.ld.input_on()

            if self.InMode4in1:
                for i in range(1, 4):
                    self.ld.select_channel(dut.slotnum + i)
                    self.current = float(config["Current"].strip("aAvV"))
                    self.ld.set_curr(self.current)  # set discharge current
                    self.ld.input_on()

            dut.status = DUT_STATUS.Discharging

        # start discharge cycle
        all_discharged = False
        fast_loop = False
        start_time = time.time()
        #self.ps.setVolt(0.0)
        while (not all_discharged):
            all_discharged = True
            for dut in self.dut_list:
                try:
                    if dut is None:
                        continue
                    config = load_test_item(self.config_list[dut.slotnum],
                                            "Discharge")
                    if (not config["enable"]):
                        continue
                    if (config["stoponfail"]) & \
                            (dut.status != DUT_STATUS.Discharging):
                        continue

                    threshold = float(config["Threshold"].strip("aAvV"))
                    max_dischargetime = config["max"]
                    min_dischargetime = config["min"]

                    self.switch_to_dut(dut.slotnum)
                    # cap_in_ltc = dut.meas_capacitor()
                    # print cap_in_ltc
                    this_cycle = Cycle()
                    this_cycle.vin = dut.meas_vin()
                    temperature = dut.check_temp()
                    this_cycle.temp = temperature
                    this_cycle.counter = self.counter
                    this_cycle.time = time.time()

                    this_cycle.state = "discharge"
                    self.ld.select_channel(dut.slotnum)
                    this_cycle.vcap = dut.meas_vcap()
                    if (this_cycle.vcap <= threshold + 0.2) & (fast_loop == False) & (self.producttype=='Garnet'):
                        fast_loop = True
                    # this_cycle.vcap = self.ld.read_volt()
                    self.counter += 1

                    discharge_time = this_cycle.time - start_time
                    dut.discharge_time = discharge_time
                    if (temperature>50 or temperature<10):
                        all_discharged &= True
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "Temperature out of range."
                        self._turn_off_load(dut.slotnum)
                    elif (discharge_time > max_dischargetime):
                        all_discharged &= True
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "Discharge Time Too Long."
                        self._turn_off_load(dut.slotnum)
                    elif (this_cycle.vin < 4.4):
                        all_discharged &= True
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "Boost voltage error."
                        self._turn_off_load(dut.slotnum)
                    elif (this_cycle.vcap < threshold):
                        all_discharged &= True
                        self._turn_off_load(dut.slotnum)
                        if (discharge_time < min_dischargetime):
                            dut.status = DUT_STATUS.Fail
                            dut.errormessage = "Discharge Time Too Short."
                        else:
                            if self.erie.GetGTGPin(dut.slotnum):
                                dut.status = DUT_STATUS.Fail
                                dut.errormessage = "GTG Pin check failed"
                            else:
                                dut.status = DUT_STATUS.Idle  # pass
                    elif (self.producttype=='Garnet'):
                        all_discharged &= False
                        if (this_cycle.vcap > 5.5):
                            if (this_cycle.vcap - this_cycle.vin >= 0.3):
                                all_discharged &= True
                                dut.status = DUT_STATUS.Fail
                                dut.errormessage = "Bypass voltage error."
                                self._turn_off_load(dut.slotnum)
                    else:
                        all_discharged &= False
                    dut.cycles.append(this_cycle)
                    logger.info("dut: {0} status: {1} vcap: {2} vout: {3} "
                                "temp: {4} message: {5} ".
                                format(dut.slotnum, dut.status, this_cycle.vcap, this_cycle.vin,
                                       this_cycle.temp, dut.errormessage))
                except aardvark.USBI2CAdapterException:
                    logger.info("dut: {0} IIC access failed.".
                                format(dut.slotnum))
                    all_discharged &= True
                    dut.status = DUT_STATUS.Fail
                    dut.errormessage = "IIC access failed."
                    self._turn_off_load(dut.slotnum)
            if not all_discharged:
                if not fast_loop:
                    time.sleep(INTERVAL)

        # check shutdown function
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Discharge")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            if config.get("Recharge", False) == "Yes":
                dut.status = DUT_STATUS.Discharging

        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Discharge")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & \
                    (dut.status != DUT_STATUS.Discharging):
                continue

            fShutdownSuccessfull = False
            self.switch_to_dut(dut.slotnum)
            self.erie.ShutdownDUT(dut.slotnum)
            try:
                dut.meas_vcap()
            except aardvark.USBI2CAdapterException:
                # if iic exception occur, DUT shutdown already
                fShutdownSuccessfull = True

            if not fShutdownSuccessfull:
                dut.errormessage = "Shutdown function error."
                dut.status = DUT_STATUS.Fail
            else:
                dut.status = DUT_STATUS.Idle
            logger.info("Shutdown process...dut: {0} "
                        "status: {1} message: {2} ".
                        format(dut.slotnum, dut.status, dut.errormessage))

    def program_dut(self):
        """ program vpd of DUT.
        :return: None
        """
        # STEP 1: check Present Pin first for hardware exist
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            self.switch_to_dut(dut.slotnum)

            logger.info("Check PGEM Present Pin for slot {0}".format(dut.slotnum))
            if not self.erie.GetPresentPin(dut.slotnum):
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "PGEM Connection Issue"
                logger.info("dut: {0} status: {1} message: {2} ".
                            format(dut.slotnum, dut.status, dut.errormessage))
            if self.InMode4in1:
                for i in range(1, 4):
                    self.switch_to_dut(dut.slotnum + i)

                    logger.info("Check PGEM Present Pin for slot {0}".format(dut.slotnum + i))
                    if not self.erie.GetPresentPin(dut.slotnum + i):
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "PGEM Connection Issue"
                        logger.info("dut: {0} status: {1} message: {2} ".
                                    format(dut.slotnum, dut.status, dut.errormessage))
        # STEP 2: turn power on
        power_on_delay = False
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            power_on_delay = True
            self.ps.selectChannel(dut.slotnum)  # no turning on shared port power coz Vin check
            self.ps.activateOutput()
            time.sleep(0.2)
        if power_on_delay:
            time.sleep(5)
        # STEP 3: check hardware ready
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            self.switch_to_dut(dut.slotnum)
            logger.info("Check PGEM Hardware Ready for slot {0}".format(dut.slotnum))
            try:
                if not self._check_hardware_ready_(dut):
                    dut.status = DUT_STATUS.Fail
                    dut.errormessage = "DUT is not ready."
            except aardvark.USBI2CAdapterException:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "IIC access failed."
                logger.info("dut: {0} status: {1} message: {2} ".
                            format(dut.slotnum, dut.status, dut.errormessage))
        # STEP 3a: check Vin
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            self.switch_to_dut(dut.slotnum)
            vin=dut.meas_vin()
            logger.info("dut: {0} measured Vin {1}".format(dut.slotnum, vin))
            if 13<vin or 10>vin:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "Vin error"
            else:
                if self.InMode4in1:
                    # test each shared port Vin
                    for i in range(1, 4):
                        self.ps.selectChannel(dut.slotnum + i)
                        self.ps.activateOutput()
                        time.sleep(0.1)
                        self.ps.selectChannel(dut.slotnum + i - 1)
                        self.ps.deactivateOutput()
                        time.sleep(1)
                        vin=dut.meas_vin()
                        logger.info("dut: {0} measured sharded port at {1} Vin {2}".format(dut.slotnum, i, vin))
                        if 13<vin or 10>vin:
                            dut.status = DUT_STATUS.Fail
                            dut.errormessage = "Vin error"
                        time.sleep(1)

                    # turn on every port
                    for i in range(0, 4):
                        self.ps.selectChannel(dut.slotnum + i)
                        self.ps.activateOutput()
                        time.sleep(0.1)
        # STEP 4: Program VPD
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            self.switch_to_dut(dut.slotnum)
            dut.status = DUT_STATUS.Program_VPD
            try:
                logger.info("dut: {0} start writing...".format(dut.slotnum))
                dut.write_vpd(config["File"])
                if self.InMode4in1:
                    # figure out a non-sequence writing method for shared port, yield a non-sequence cable sequence
                    s0 = s1 = s2 = False
                    for i in range(1, 4):
                        self.switch_to_dut(dut.slotnum + i)
                        addr = dut.write_shared_vpd(config["File"])
                        logger.info("shared port: {0} writed at address 0x{1:x}...".format(dut.slotnum + i, addr))
                        if addr == 0x54:
                            s0 = True
                        elif addr == 0x55:
                            s1 = True
                        elif addr == 0x56:
                            s2 = True

                    if not(s0 and s1 and s2):
                        raise aardvark.USBI2CAdapterException
                dut.program_vpd = 1
                if config.get("Flush_EE",False)=="Yes":
                    self.switch_to_dut(dut.slotnum)
                    dut.flush_ee()
                else:
                    self._turn_off_power(dut.slotnum)
                    time.sleep(1)
            except AssertionError:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "Programming VPD Fail"
                logger.info("dut: {0} status: {1} message: {2} ".
                            format(dut.slotnum, dut.status, dut.errormessage))
            except aardvark.USBI2CAdapterException:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "IIC access failed."
                logger.info("dut: {0} status: {1} message: {2} ".
                            format(dut.slotnum, dut.status, dut.errormessage))

        # STEP 5: turn power on again if needed
        power_on_delay = False
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Program_VPD):
                continue
            self.ps.selectChannel(dut.slotnum)
            if not self.ps.isOutputOn():
                power_on_delay = True
                self.ps.activateOutput()
                time.sleep(0.1)
                if self.InMode4in1:
                    for i in range(1, 4):
                        self.ps.selectChannel(dut.slotnum + i)
                        self.ps.activateOutput()
                        time.sleep(0.1)
        if power_on_delay:
            time.sleep(5)
        # STEP 6: check hardware ready and perform RESET
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Program_VPD):
                continue
            self.switch_to_dut(dut.slotnum)

            try:
                if not self._check_hardware_ready_(dut):
                    dut.status = DUT_STATUS.Fail
                    dut.errormessage = "DUT is not ready."
                else:
                    self.erie.ResetDUT(dut.slotnum)
                    dut.status = DUT_STATUS.Idle
            except aardvark.USBI2CAdapterException:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "IIC access failed."
                logger.info("dut: {0} status: {1} message: {2} ".
                            format(dut.slotnum, dut.status, dut.errormessage))

    def check_vpd(self):

        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            if dut.status != DUT_STATUS.Idle:
                continue

            self.ps.selectChannel(dut.slotnum)
            if not self.ps.isOutputOn():
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "No Power output, STOP checking VPD"

            if self.InMode4in1:
                for i in range(1, 4):
                    self.switch_to_dut(dut.slotnum + i)

                    self.ps.selectChannel(dut.slotnum + i)
                    if not self.ps.isOutputOn():
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "No Power output, STOP checking VPD"

        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Program_VPD")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            self.switch_to_dut(dut.slotnum)

            try:
                dut.read_vpd()
                if not dut.check_vpd():
                    dut.status = DUT_STATUS.Fail
                    dut.errormessage = "Checking VPD error."
                else:
                    dut.hwver = dut.read_hw_version()
                    logger.info("dut: {0} checking hardware version = {1}".format(dut.slotnum, dut.hwver))
                    if dut.hwver=='255':
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "HW ver error."
                    else:
                        dut.fwver = dut.read_fw_version()
                        logger.info("dut: {0} checking firmware version = {1}".format(dut.slotnum, dut.fwver))
                        if config.get("FWver", False):
                            if not dut.fwver==config["FWver"]:
                                dut.status = DUT_STATUS.Fail
                                dut.errormessage = "FW ver error."
            except aardvark.USBI2CAdapterException:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "IIC access failed."

    def check_temperature_dut(self):
        """
        check temperature value of IC on DUT.
        :return: None.
        """
        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Check_Temp")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            self.switch_to_dut(dut.slotnum)
            temp = dut.check_temp()
            if not (config["min"] < temp < config["max"]):
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "Temperature out of range."
                logger.info("dut: {0} status: {1} message: {2} ".
                            format(dut.slotnum, dut.status, dut.errormessage))

    def switch_to_dut(self, slot):
        self.adk.select_channel(slot)
    
    def calculate_capacitance(self):
        """ calculate the capacitance of DUT, based on vcap list in discharging.
        :return: capacitor value
        """

        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Capacitor")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            if dut.status != DUT_STATUS.Idle:
                continue

            self.ps.selectChannel(dut.slotnum)
            if not self.ps.isOutputOn():
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "No Power output, STOP cap measure"

            if self.InMode4in1:
                for i in range(1, 4):
                    self.switch_to_dut(dut.slotnum + i)

                    self.ps.selectChannel(dut.slotnum + i)
                    if not self.ps.isOutputOn():
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "No Power output, STOP cap measure"

        for dut in self.dut_list:
            if dut is None:
                continue
            config = load_test_item(self.config_list[dut.slotnum],
                                    "Capacitor")
            if (not config["enable"]):
                continue
            if (config["stoponfail"]) & (dut.status != DUT_STATUS.Idle):
                continue
            if dut.status != DUT_STATUS.Idle:
                continue

            self.switch_to_dut(dut.slotnum)
            try:
                if (self.producttype=='Jamber'):
                    dut.start_cap_ext()
                else:
                    dut.start_cap()
            except aardvark.USBI2CAdapterException:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "IIC access failed."
            #time.sleep(1)
            dut.status = DUT_STATUS.Cap_Measuring
            logger.info("started cap measure")

        #close load and set PS
        #self.ld.reset()
        #time.sleep(2)
        # setup power supply
        #self.ps.selectChannel(node=PS_ADDR, ch=PS_CHAN)
        setting = {"volt": PS_VOLT, "curr": PS_CURR,
                   "ovp": PS_OVP, "ocp": PS_OCP}
        #self.ps.set(setting)
        #self.ps.activateOutput()
        time.sleep(1)
        start_time = time.time()

        all_cap_mears=False
        while not all_cap_mears:
            all_cap_mears=True
            for dut in self.dut_list:
                try:
                    if dut is None:
                        continue
                    if dut.status != DUT_STATUS.Cap_Measuring:
                        continue
                    self.switch_to_dut(dut.slotnum)

                    config = load_test_item(self.config_list[dut.slotnum],
                                    "Capacitor")
                    if "Overtime" in config:
                        overtime=float(config["Overtime"])
                    else:
                        overtime=600

                    #self.adk.slave_addr = 0x14
                    #val = self.adk.read_reg(0x23,0x01)[0]
                    val = dut.read_PGEMSTAT(0)
                    #logger.info("PGEMSTAT.BIT2: {0}".format(val))
                    vcap_temp=dut.meas_vcap()
                    logger.info("dut: {0} PGEMSTAT.BIT2: {1} vcap in cap calculate: {2}".format(dut.slotnum, val, vcap_temp))

                    capacitor_time = time.time() - start_time
                    dut.capacitor_time = capacitor_time

                    if (val | 0xFB)==0xFB: #PGEMSTAT.BIT2==0 CAP MEASURE COMPLETE
                        all_cap_mears &= True
                        val1 = dut.read_vpd_byaddress(0x100)[0] #`````````````````````````read cap vale from VPD``````````compare````````````````````````````
                        logger.info("capacitance_measured value: {0}".format(val1))
                        dut.capacitance_measured=val1
                        if not (config["min"] < val1 < config["max"]):
                            dut.status=DUT_STATUS.Fail
                            dut.errormessage = "Cap is over limits"
                            logger.info("dut: {0} capacitor: {1} message: {2} ".
                                format(dut.slotnum, dut.capacitance_measured,
                                   dut.errormessage))
                        else:
                            dut.status = DUT_STATUS.Idle  # pass
                    elif capacitor_time > overtime:
                        all_cap_mears &= True
                        dut.status=DUT_STATUS.Fail
                        dut.errormessage = "Cap start over time"
                        logger.info("dut: {0} capacitor: {1} message: {2} ".
                            format(dut.slotnum, dut.capacitance_measured,
                                   dut.errormessage))
                    else:
                        all_cap_mears &= False
                except aardvark.USBI2CAdapterException:
                    logger.info("dut: {0} IIC access failed.".
                                format(dut.slotnum))
                    all_cap_mears &= True
                    dut.status = DUT_STATUS.Fail
                    dut.errormessage = "IIC access failed."
            if not all_cap_mears:
                time.sleep(INTERVAL * 5)

        #check capacitance ok
        for dut in self.dut_list:
            all_cap_ready=True
            if dut is None:
                continue
            if dut.status != DUT_STATUS.Idle:
                continue
            self.switch_to_dut(dut.slotnum)
            #self.adk.slave_addr = 0x14
            #val = self.adk.read_reg(0x21,0x01)[0]
            try:
                val = dut.read_GTG(0)
                if not((val&0x02)==0x02):
                    dut.status=DUT_STATUS.Fail
                    dut.errormessage = "GTG.bit1 ==0 "
                    logger.info("GTG.bit1 ==0")
                # check GTG_WARNING == 0x00
                #temp=self.adk.read_reg(0x22)[0]
                else:
                    temp = dut.read_GTG_WARN(0)
                    logger.info("GTG_Warning value: {0}".format(temp))
                    if not (temp==0x00):
                        dut.status = DUT_STATUS.Fail
                        dut.errormessage = "GTG_warning != 0x00"
                    else:
                        #dut.status = DUT_STATUS.Idle    # pass
                        if not self.erie.GetGTGPin(dut.slotnum):
                            dut.status = DUT_STATUS.Fail
                            dut.errormessage = "GTG Pin check failed"
                        else:
                            if self.InMode4in1:
                                all_GTG = True
                                for i in range(1, 4):
                                    self.switch_to_dut(dut.slotnum + i)
                                    if not self.erie.GetGTGPin(dut.slotnum + i):
                                        all_GTG &= False

                                if all_GTG:
                                    dut.status = DUT_STATUS.Idle  # pass
                                else:
                                    dut.status = DUT_STATUS.Fail
                                    dut.errormessage = "GTG Pin check failed"
                            else:
                                dut.status = DUT_STATUS.Idle  # pass
            except aardvark.USBI2CAdapterException:
                dut.status = DUT_STATUS.Fail
                dut.errormessage = "IIC access failed."

    def save_db(self):
        # setup database
        # db should be prepared in cli.py
        try:
            sm = SessionManager()
            sm.prepare_db("sqlite:///" + RESULT_DB, [DUT, Cycle])
            session = sm.get_session("sqlite:///" + RESULT_DB)

            for dut in self.dut_list:
                if dut is None:
                    continue
                for pre_dut in session.query(DUT). \
                        filter(DUT.barcode == dut.barcode, DUT.archived == 0).all():
                    pre_dut.archived = 1
                    session.add(pre_dut)
                    session.commit()
                dut.archived = 0
                session.add(dut)
                session.commit()
            session.close()
        except Exception as e:
            self.error(e)

    def save_file(self):
        """ save dut info to xml file
        :return:
        """
        for dut in self.dut_list:
            if dut is None:
                continue
            if not os.path.exists(RESULT_LOG):
                os.makedirs(RESULT_LOG)
            filename = dut.barcode + ".xml"
            filepath = os.path.join(RESULT_LOG, filename)
            i = 1
            while os.path.exists(filepath):
                filename = "{0}({1}).xml".format(dut.barcode, i)
                filepath = os.path.join(RESULT_LOG, filename)
                i += 1
            result = simplexml.dumps(dut.to_dict(), "entity")
            with open(filepath, "wb") as f:
                f.truncate()
                f.write(result)

    def prepare_to_exit(self):
        """ cleanup and save to database before exit.
        :return: None
        """

        if self.dutnumber == 0:
            self.channelresult = BOARD_STATUS.Idle
        else:
            self.channelresult = BOARD_STATUS.Pass

        for dut in self.dut_list:
            if dut is None:
                continue
            if (dut.status == DUT_STATUS.Idle):
                dut.status = DUT_STATUS.Pass
                msg = "passed"
            else:
                self.channelresult = BOARD_STATUS.Fail
                self.erie.LedOn(dut.slotnum)
                msg = dut.errormessage
            logger.info("TEST RESULT: dut {0} ===> {1}".format(
                dut.slotnum, msg))

        for slot in range(TOTAL_SLOTNUM):
            self.ps.selectChannel(slot)
            self.ps.deactivateOutput()

        # save to xml logs
        self.save_file()

        # power off
        #self.ps.deactivateOutput()

    def run(self):
        """ override thread.run()
        :return: None
        """
        while (not self.exit):
            state = self.queue.get()
            if (state == ChannelStates.EXIT):
                try:
                    self.prepare_to_exit()
                    self.exit = True
                    logger.info("Channel: Exit Successfully.")
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.INIT):
                try:
                    logger.info("Channel: Initialize.")
                    self.init()
                    self.progressbar += 20
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.CHARGE):
                try:
                    logger.info("Channel: Charge DUT.")
                    self.charge_dut()
                    self.progressbar += 20
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.HOLD):
                try:
                    logger.info("Channel: Hold Power On.")
                    self.hold_power_on()
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.LOAD_DISCHARGE):
                try:
                    logger.info("Channel: Discharge DUT.")
                    self.discharge_dut()
                    self.progressbar += 15
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.PROGRAM_VPD):
                try:
                    logger.info("Channel: Program VPD.")
                    self.program_dut()
                    self.progressbar += 5
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.CHECK_VPD):
                try:
                    logger.info("Channel: Check VPD")
                    self.check_vpd()
                    self.progressbar += 5
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.CHECK_CAPACITANCE):
                try:
                    logger.info("Channel: Check Capacitor Value")
                    self.calculate_capacitance()
                    self.progressbar += 30
                except Exception as e:
                    self.error(e)
            elif (state == ChannelStates.RECHARGE):
                try:
                    logger.info("Channel: Recharge DUT")
                    self.recharge_dut()
                    self.progressbar += 5
                except Exception as e:
                    self.error(e)
            else:
                logger.error("unknown dut state, exit...")
                self.exit = True

    def auto_test(self):
        self.queue.put(ChannelStates.INIT)
        self.queue.put(ChannelStates.PROGRAM_VPD)
        self.queue.put(ChannelStates.CHARGE)
        if HOLD_EN:
            self.queue.put(ChannelStates.HOLD)
        #self.queue.put(ChannelStates.PROGRAM_VPD)
        self.queue.put(ChannelStates.CHECK_CAPACITANCE)
        #self.queue.put(ChannelStates.CHECK_ENCRYPTED_IC)
        self.queue.put(ChannelStates.CHECK_VPD)
        #self.queue.put(ChannelStates.CHECK_POWER_FAIL)
        # self.queue.put(ChannelStates.DUT_DISCHARGE)
        self.queue.put(ChannelStates.LOAD_DISCHARGE)
        self.queue.put(ChannelStates.RECHARGE)
        self.queue.put(ChannelStates.EXIT)
        self.start()

    def empty(self):
        for i in range(self.queue.qsize()):
            self.queue.get()

    def error(self, e):
        exc = sys.exc_info()
        logger.error(traceback.format_exc(exc))
        self.exit = True
        raise e

    def quit(self):
        self.empty()
        self.queue.put(ChannelStates.EXIT)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # barcode = ["AGIGA9603-004BCA02144800000002-06",
    #            "AGIGA9603-004BCA02144800000002-06",
    #            "AGIGA9603-004BCA02144800000002-06",
    #            "AGIGA9603-004BCA02144800000002-06"]
    barcode = ["AGIGA9811-001BCA02143900000228-01"]
    ch = Channel(barcode_list=barcode, channel_id=0,
                 name="UFT_CHANNEL", cable_barcodes_list=[""])
    # ch.start()
    # ch.queue.put(ChannelStates.INIT)
    # ch.queue.put(ChannelStates.CHARGE)
    # ch.queue.put(ChannelStates.PROGRAM_VPD)
    # ch.queue.put(ChannelStates.CHECK_ENCRYPTED_IC)
    # ch.queue.put(ChannelStates.CHECK_TEMP)
    # ch.queue.put(ChannelStates.LOAD_DISCHARGE)
    # ch.queue.put(ChannelStates.CHECK_CAPACITANCE)
    # ch.queue.put(ChannelStates.EXIT)
    ch.auto_test()
    # ch.switch_to_mb()
    # ch.switch_to_dut(0)
    # ch.init()
    # ch.charge_dut()
    # ch.discharge_dut()
