import argparse
import base64
import logging
import smtplib
import sys
import time
from collections import deque
from logging.handlers import RotatingFileHandler
import requests

from email_creds import email_creds
from creds import dyndns_creds


URL = f'https://www.dy.fi/nic/update?hostname={dyndns_creds["domain"]}'
GLOBAL_LOG_LEVEL = logging.INFO
LOG_FILE = 'dyndns_update.log'
CHECK_INTERVAL = 5
FORCE_UPDATE_INTERVAL_DAYS = 2
logger = logging.getLogger()


def setup_logging():
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%d.%m.%Y %H:%M:%S')
    handler = RotatingFileHandler(LOG_FILE, mode='a', maxBytes=5*1024*1024, backupCount=2, encoding='utf-8', delay=0)
    handler.setFormatter(formatter)
    handler.setLevel(GLOBAL_LOG_LEVEL)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    log = logging.getLogger()
    log.setLevel(GLOBAL_LOG_LEVEL)
    log.addHandler(handler)
    log.addHandler(stream_handler)


def get_ip_address():
    try:
        return requests.get('https://api.ipify.org?format=json', timeout=30).json()['ip']
    except Exception as e:
        logger.warning('Could not get IP address from API: {}'.format(str(e)))
        return ''


def update_dyndns(ip_address):
    logger.info(f'Updating dy.fi DNS for {dyndns_creds["domain"]}')
    try:
        r = requests.get(URL, auth=(dyndns_creds['user'], dyndns_creds['pass']), timeout=30)
    except Exception as e:
        logger.error('Could not update dy.fi DNS: {}'.format(str(e)))
        return False
    if r.status_code == 200:
        logger.info('Updated successfully to {}'.format(ip_address))
    else:
        logger.warning('dy.fi DNS returned status code {}, update failed'.format(r.status_code))
        return False
    return True


def force_update_reached(times_checked):
    return times_checked >= FORCE_UPDATE_INTERVAL_DAYS * 24 * 60 // CHECK_INTERVAL


def get_latest_logs():
    with open(LOG_FILE) as handle:
        return ''.join(deque(handle, 10))


def send_email_with_ip(ip_address):
    latest_logs = get_latest_logs()
    message = f'From: {email_creds["user"]}@gmail.com\nTo: {dyndns_creds["recipient_email"]}\nSubject: DNS updated for dy.fi\n\nIP address: {ip_address}\n\n{latest_logs}'
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(f'{email_creds["user"]}@gmail.com', base64.b64decode(email_creds['password']).decode('ascii'))
        server.sendmail(f'{email_creds["user"]}@gmail.com', dyndns_creds['recipient_email'], message)
        server.close()
        logger.info(f'Sent mail to {dyndns_creds["recipient_email"]}')
    except Exception as e:
        logger.error('Sending mail failed: {}'.format(str(e)))


def main(args):
    setup_logging()
    logger.info('Dynamic DNS updater started')
    logger.info('IP address check interval is {} minutes'.format(CHECK_INTERVAL))
    prev_ip_address = get_ip_address()
    times_checked = 0
    while True:
        ip_address = get_ip_address()
        logger.info('Current IP address is {}'.format(ip_address))
        if ip_address and args.force:
            logger.info('Forcing IP address change because of the force argument')
            success = update_dyndns(ip_address)
            if success:
                logger.info('IP updated successfully')
            send_email_with_ip(ip_address)
            sys.exit(0)
        if ip_address and (prev_ip_address != ip_address or force_update_reached(times_checked)):
            if force_update_reached(times_checked):
                logger.info('Forcing IP address update after {} checks ({} days)'.format(times_checked, FORCE_UPDATE_INTERVAL_DAYS))
            else:
                logger.info('IP address change detected ({}, previously {})'.format(ip_address, prev_ip_address))
            success = update_dyndns(ip_address)
            if success:
                prev_ip_address = ip_address
                logger.info('IP updated successfully')
                times_checked = 0
            else:
                logger.error('IP update failed')
            send_email_with_ip(ip_address)
        times_checked += 1
        time.sleep(CHECK_INTERVAL * 60)


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Force single update')
    return parser.parse_args()


if __name__ == '__main__':
    main(get_arguments())
