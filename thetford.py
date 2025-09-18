#!/usr/bin/env python3

# Retrieve status from thetford N4000/T2000 series refrigerator
# modified by Sönke Krebber for different MQTT topic/value concept. 3.9.2024 

import sys
import syslog
import time
import argparse
import json
import paho.mqtt.client as paho

from usblini import USBlini

syslog.openlog(ident="thetfordmqtt",logoption=syslog.LOG_PID)

def tell(level, msg):
	if args.v >= level:
		if args.l:
			syslog.syslog(syslog.LOG_INFO, msg)
		else:
			print(msg)

received = 0

titles = {
	0  : "Supply",
	1  : "Level",
	2  : "Dplus",
	3  : "Status",
	4  : "ExtSupply",
	5  : "IntSupply",
	6  : "",
	7  : "",
	10 : "Mode"
}

unitsN = {
	0  : "",
	1  : "",
	2  : "",
	3  : "",
	4  : "V",
	5  : "V",
	6  : "",
	7  : "",
	10 : ""
}

unitsT = {
	0  : "",
	1  : "",
	2  : "",
	3  : "",
	4  : "",
	5  : "V",
	6  : "",
	7  : "",
	10 : ""
}

def toSensorTitle(byte):
	return titles[byte];

def toSensorUnit(byte):
	if args.M.strip() == "N4000":
		return unitsN[byte];
	return unitsT[byte];

def byte2uint(val):
	if val < 0:
		return -(256-val)
	else:
		return val

def toError(code):
	if code == 0:
		return "Online"
	if code == 3:
		return "Fehler Gas"
	if code == 4:
		return "Fehler 12V Heizstab"
	if code == 6:
		return "Fehler 12V"
	if code == 7:
		return "Fehler D+"
	if code == 8:
		return "Fehler 230V Heizstab"
	if code == 9:
		return "Fehler Steuerung"
	if code == 10:
		return "Fehler 230V"
	if code == 11:
		return "Keine Energiequelle"
	if code == 13:
		return "Fehler Temp Fühler"
	if code == 23:
		return "Störung 23"

	tell(0, '{0:} {1:}'.format("Unexpected status code", code))

	return "Störung?"

def isAuto(val):
	if val & 0x08:
		return True

	return False

def toModeString(mode):
	mode = mode & ~0x08     # mask additional auto bit, we check it by isAuto
	if mode == 0:
		return "Aus"
	elif mode == 1:
		return "An"
	elif mode == 2:
		return "Aus"
	elif mode == 3:
		return "Gas"
	elif mode == 4:
		return "4 Störung Batt?"
	elif mode == 5:
		return "Batterie"
	elif mode == 6:
		return "6 Störung?"
	elif mode == 7:
		return "Netz ~230V"
	elif mode == 9:
		return "Nacht"
	return str(mode)

def open():
	while True:
		try:
			ulini.open()
			ulini.set_baudrate(19200)
			print("Open succeeded")
			break;     # open succeeded
		except:
			print("Open failed, USBlini device with id '04d8:e870' not found, aborting, check connection and cable")
			print("Retrying in 5 seconds ..")
			time.sleep(5.0)

def publishMqtt(sensor):
	if args.m.strip() != '':
		title = sensor.pop("title")
		msg = json.dumps(sensor)
		tell(2, '{}'.format(msg))
		ret = mqtt.publish(args.T.strip()+"/"+title, msg)

def frame_listener(frame):

	if frame.frameid != 0x0c:
		return

	global received
	received += 1

	tell(0, 'Updating ...')
	tell(2, '-----------------------')

	for byte in range(8):
		tell(1, 'Byte {0:}: 0b{1:08b} 0x{1:02x} ({1:})'.format(byte, byte2uint(frame.data[byte])))

		# build JSON for topic n4000:
		#  {"type": "N4000", "address": 3, "value": 0, "title": "Status", "text": "Online"}
        #  {"title": "Status", "byte": "0", "value": 0, "unit": "V"}

		sensor = {
			'title'   : toSensorTitle(byte),
            'byte'   : byte2uint(frame.data[byte])
		}

		

		if byte == 0:
			sensor['value'] = toModeString(sensor['byte'])
			tell(3, '{0:} / {1:}'.format(toModeString(sensor['byte']), "Automatik" if isAuto(sensor['byte']) else "Manuell"))
		elif byte == 1:
			if args.M.strip() == "N4000": 
				sensor['value'] = sensor['byte']+1
				tell(3, '{}: {} {}'.format(toSensorTitle(byte), sensor['byte'], toSensorUnit(byte)))
			else:
				sensor['value'] = sensor['byte']
				tell(3, '{}: {} {}'.format(toSensorTitle(byte), sensor['byte'], toSensorUnit(byte)))

				freezer = sensor['value']>>4
				fridge = sensor['value']-((sensor['value']>>4)<<4)

				#if sensor['value'] > 48:
				#	freezer = 3
				#elif sensor['value'] > 32:
				#	freezer = 2
				#elif sensor['value'] > 16:
				#	freezer = 1
				#else:
				#	freezer = 0
				#fridge = sensor['value'] - 16 * freezer
				publishMqtt({'title' : 'LvlFridge', 'value' : fridge})
				publishMqtt({'title' : 'LvlFreezer', 'value' : freezer})
		elif byte == 2:
			if args.M.strip() == "N4000":
			    sensor['value'] = sensor['byte'] & 0x40 > 0
			tell(3, '{}: {} {}'.format(toSensorTitle(byte), sensor['byte'], toSensorUnit(byte)))
		elif byte == 3:
			sensor['value'] = toError(sensor['byte'])
			tell(3, '{0:} {1:}'.format("Status", sensor['byte']))
		elif byte == 4:
			if args.M.strip() == "N4000":
				sensor['value'] = sensor['byte']
			tell(3, '{}: {} {}'.format(toSensorTitle(byte), sensor['byte'], toSensorUnit(byte)))
		elif byte == 5:
			sensor['value'] = sensor['byte'] / 10
			tell(3, '{}: {} {}'.format(toSensorTitle(byte), sensor['byte'], toSensorUnit(byte)))

		unit = toSensorUnit(byte)
		if unit != "":
			sensor['unit'] = unit
		
		if ((byte in [0,1,2,3,4,5]) & (args.M.strip() == "N4000")) | ((byte in [0,1,3,5]) & (args.M.strip() == "T2000")):
			publishMqtt(sensor)

		if args.M.strip() == "N4000":
			if byte == 0:
				sensor = {
					'title'   : toSensorTitle(10),
					'byte'   : byte2uint(frame.data[byte]) & 0x08,
					'value'    : "Automatik" if isAuto(byte2uint(frame.data[byte])) else "Manuell"
				}
				publishMqtt(sensor)

	tell(0, "... done")

# --------------------------------------------

# arguments

parser = argparse.ArgumentParser('thetford')
parser.add_argument('-i', type=int, nargs='?', help='interval [seconds] (default 5)', default=5)
parser.add_argument('-m',           nargs='?', help='MQTT host', default="")
parser.add_argument('-p', type=int, nargs='?', help='MQTT port', default=1883)
parser.add_argument('-u',           nargs='?', help='MQTT user', default="")
parser.add_argument('-P',           nargs='?', help='MQTT password', default="")
parser.add_argument('-v', type=int, nargs='?', help='Verbosity Level (0-3) (default 1)', default=1)
parser.add_argument('-c', type=int, nargs='?', help='Sample Count', default=0)
parser.add_argument('-l', action='store_true', help='Log to Syslog (default console)')
parser.add_argument('-T',           nargs='?', help='MQTT topic', default="n4000")
parser.add_argument('-M',           nargs='?', help='Fridge model', default="N4000")

args = parser.parse_args()

# open mqtt connection

if args.m.strip() != '':
	tell(0, 'Connecting to "{}:{}", topic "{}"'.format(args.m.strip(), args.p, args.T.strip()))
	mqtt = paho.Client("thetford")
	mqtt.username_pw_set(args.u.strip(), args.P.strip())
	mqtt.connect(args.m.strip(), args.p)

# init usblini

ulini = USBlini()
open()

# send one frame to wakeup devices

ulini.master_write(0x00, USBlini.CHECKSUM_MODE_NONE, [])
time.sleep(0.2)

# add listener and set master sequence

ulini.frame_listener_add(frame_listener)
ulini.master_set_sequence(args.i * 1000, 200, [0x0c])

while True:
	time.sleep(1.0)
	abort = args.c != 0 and received >= args.c
	if abort:
		break
	pass

ulini.close()

if args.m.strip() != '':
	mqtt.disconnect()