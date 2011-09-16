#!/bin/python

import dbus
import os
import signal
import socket
import string
import time

users = []

bus = dbus.SessionBus()

api = None
me = None
pid = None

MYPORT =  37957 # EPYKS on a mobile phone keypad

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
    skype = bus.get_object('com.Skype.API', '/com/Skype')
    
    global api
    
    api = skype.get_dbus_method('Invoke', 'com.Skype.API')
    
    response = api('NAME checkskype.py')
    
    if response != 'OK':
        raise dbus.exceptions.DBusException() # Probably Skype is running but not signed in
    
    api('PROTOCOL 5')
    
    global me
    
    me = arg(api('GET CURRENTUSERHANDLE'), -1)
    
    global pid
    
    dbusinfo = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
    
    pid = dbusinfo.GetConnectionUnixProcessID('com.Skype.API')

def getstatus (username = None):
    if username:
        status = api('GET USER %s ONLINESTATUS' % username)
    else:
        status = api('GET USERSTATUS')
    
    return arg(status, -1)

def checkuser (user):
    if user == me:
        return
    
    status = getstatus(user)
    
    if status != 'OFFLINE':
        return
    
    print '%s is offline!' % user
    
    # TODO: stop sending these after 2 mins or so
    sendudp(user)

def update ():
    messages = getudp()
    
    # Check if anyone else thinks we are offline
    for user in messages:
        if user == me:
            # TODO: require multiple messages to believe it
            restart()
    
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
        time.sleep(60)
    except PleaseRestart:
        os.kill(pid, signal.SIGKILL)
        os.system('skype &')
        # Wait and try to re-attach to the new instance of Skype
        time.sleep(60)

