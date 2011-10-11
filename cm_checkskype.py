#! /usr/bin/env python

import dbus
import os
import signal
import socket
import string
import time
import logging
import logging.handlers

my_logger = logging.getLogger('CMSkype')
my_logger.setLevel(logging.DEBUG)

handler = logging.handlers.SysLogHandler(address = '/dev/log')

my_logger.addHandler(handler)


users = []

bus = dbus.SessionBus()

api = None
me = None
pid = None

MYPORT =  37958 # EPYKS on a mobile phone keypad

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('', MYPORT))
s.setblocking(0)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

def getudp ():
    list = []
    
    while True:
        try:
            data, addr = s.recvfrom(1024) # buffer size is 1024 bytes
            list.append(data)
        except socket.error:
            return list

def sendudp (data):
    s.sendto(data, ('<broadcast>', MYPORT))

class PleaseRestart(Exception):
    pass

def restart ():
    # Only try to restart if Skype thinks that we're online (otherwise we probably haven't crashed)
    
    status = getstatus()
    
    if status == 'OFFLINE':
        return # We are set to appear offline

    # This exception is caught by the main loop
    raise PleaseRestart()

def arg(s, arg):
    parts = string.split(s)
    
    return parts[arg]

def attach ():
    my_logger.info('Attaching to skype')
    
    skype = bus.get_object('com.Skype.API', '/com/Skype')
    
    global api
    
    api = skype.get_dbus_method('Invoke', 'com.Skype.API')
    
    response = api('NAME checkskype.py')
    
    if response != 'OK':
        raise dbus.exceptions.DBusException() # Probably Skype is running but not signed in
    
    api('PROTOCOL 5')
    
    global me
    
    me = arg(api('GET CURRENTUSERHANDLE'), -1)
    
    my_logger.debug('Logged into skype as: %s', me)
    
    global pid
    
    dbusinfo = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
    
    pid = dbusinfo.GetConnectionUnixProcessID('com.Skype.API')
    
    my_logger.debug('Skype process id found: %d', pid)
    
    my_logger.info('Successfully attached to skype')

def getstatus (username = None):
    if username:
        status = api('GET USER %s ONLINESTATUS' % username)
    else:
        status = api('GET USERSTATUS')
    
    return arg(status, -1)

def checkuser (user):
    if user == me:
        return
    
    my_logger.debug('Checking status of user: %s', user)
    
    status = getstatus(user)
    
    if status != 'OFFLINE':
        return
    
    my_logger.debug('%s is offline!', user)
    
    # TODO: stop sending these after 2 mins or so
    broadcast_offline(user)
    
def broadcast_self():
    send_message('nick', me)

def broadcast_offline(user):
    send_message('off', user)

def send_message(type, message):
    packet = [type, message]
    sendudp('|'.join(packet))
    
def decode_message(packet):
    return packet.split('|', 1)

def process_messages(packets):
    # Check if anyone else thinks we are offline
    for packet in packets:
        message = decode_message(packet)
        if message[0] == 'nick':
            process_message_nick(message[1])
        elif message[0] == 'off':
            process_message_off(message[1])
        else:
            my_logger.debug('Received unknown message: %s (%s)' , packet, message[0])

def process_message_nick(nick):
    global users
    if nick not in users:
        if nick != me:
            my_logger.info('Now checking for user: %s', nick)
            users.append(nick)
        
def process_message_off(nick):
    if nick == me:
        #TODO:  only restart when we get a few of these.
        restart()
    
def update ():    
    # Broadcast ourselves as being online
    broadcast_self()
    
    packets = getudp()
    process_messages(packets)
    
    # Check if we think anyone else is offline
    for user in users:
        checkuser(user)

while True:
    try:
        attach()
        
        while True:
            update()
            time.sleep(30)
    except dbus.exceptions.DBusException:
        # Skype is probably not running: be patient and maybe it'll come along later
        my_logger.info('Could not attach to skype, waiting 10s to try again...')
        time.sleep(10)
    except PleaseRestart:
        my_logger.info('Caught skype crash, restarting...')
        os.kill(pid, signal.SIGKILL)
        os.system('skype &')
        # Wait and try to re-attach to the new instance of Skype
        time.sleep(60)

# Clean up.
s.close()
