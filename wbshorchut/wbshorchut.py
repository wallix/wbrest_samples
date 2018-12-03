#!/usr/bin/python -O

from requests import Session
import urllib3
import sys
import getpass
import argparse

def get_target(user, right):
    if right['account_mapping']:
        target = "{}@{}:{}:{}".format(user, right['device'], right['service'], user)
    elif right['interactive_login']:
        target = "{}@{}:{}:{}".format("Interactive", right['device'], right['service'], user)
    else:
        target = "{}@{}@{}:{}:{}".format(right['account'], right['domain'], right['device'], right['service'], user)

    return target


def generate_rdp_config_file(filename, parameters, user, host, subprotocols,
                             application_cn, remoteapp=None, remoteappmode=False):
    
    """Create a RDP Configuration file."""

    rdp_cfg_template = [
        "screen mode id:i:1",
        "session bpp:i:%s" % parameters['rdp_color_bpp'],
        "auto connect:i:1",
        "compression:i:1",
        "keyboardhook:i:2",
        "audiomode:i:2",
        "displayconnectionbar:i:1",
        "alternate shell:s:",
        "shell working directory:s:",
        "disable wallpaper:i:1",
        "disable full window drag:i:1",
        "disable menu anims:i:1",
        "disable themes:i:1",
        "bitmapcachepersistenable:i:1",
        "prompt for credentials:i:1",
    ]

    # resolution
    if parameters["rdp_resolution"] == "fullscreen":
        rdp_cfg_template.append("screen mode id:i:2")
        rdp_cfg_template.append("multimon:i:0")
    elif parameters["rdp_resolution"] == "multimonitor":
        rdp_cfg_template.append("use multimon:i:1")
    else:
        rdp_cfg_template.append("desktopwidth:i:%s" %
                                parameters['rdp_width'])
        rdp_cfg_template.append("desktopheight:i:%s" %
                                parameters['rdp_height'])
        rdp_cfg_template.append("use multimon:i:0")

    # RDP options
    if '*' in subprotocols or 'RDP_DRIVE' in subprotocols:
        rdp_cfg_template.append("redirectdrives:i:1")
        rdp_cfg_template.append("drivestoredirect:s:*")

    else:
        rdp_cfg_template.append("redirectdrives:i:0")
        rdp_cfg_template.append("drivestoredirect:s:")

    if '*' in subprotocols or 'RDP_PRINTER' in subprotocols:
        rdp_cfg_template.append("redirectprinters:i:1")
    else:
        rdp_cfg_template.append("redirectprinters:i:0")

    if '*' in subprotocols or \
            'RDP_CLIPBOARD_UP' in subprotocols or \
            'RDP_CLIPBOARD_DOWN' in subprotocols or \
            'RDP_CLIPBOARD_FILE' in subprotocols:
        rdp_cfg_template.append("redirectclipboard:i:1")
    else:
        rdp_cfg_template.append("redirectclipboard:i:0")
    if '*' in subprotocols or 'RDP_COM_PORT' in subprotocols:
        rdp_cfg_template.append("redirectcomports:i:1")
    else:
        rdp_cfg_template.append("redirectcomports:i:0")
    if '*' in subprotocols or 'RDP_SMARTCARD' in subprotocols:
        rdp_cfg_template.append("redirectsmartcards:i:1")
    else:
        rdp_cfg_template.append("redirectsmartcards:i:0")

    if remoteappmode and application_cn:
        rdp_cfg_template.append("remoteapplicationmode:i:1")
        if remoteapp:
            rdp_cfg_template.append(
                "loadbalanceinfo:s:{}".format(remoteapp["token"])
            )
        remoteappprogram = "||WABRemoteApp{}".format(
            (":" + remoteapp["program"].encode('utf-8')
             if remoteappmode and remoteapp else "")
        )

        rdp_cfg_template.append(
            "remoteapplicationprogram:s:{}".format(remoteappprogram)
        )

    lines = rdp_cfg_template
    lines.append('full address:s:' + host)
    lines.append('username:s:' + user)
        
    with open(filename, encoding='utf-16-le', mode='w') as output:
        output.write("")  # write BOM
        for line in lines:
            # write data without BOM
            output.write(line + "\n")

def main():
    
    urllib3.disable_warnings()
 
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--application', default=None, type=str)
    group.add_argument('--device', default=None, type=str)
    
    parser.add_argument('--account', default=None, type=str)
    parser.add_argument('--domain', default=None, type=str)

    parser.add_argument('--resolution', default=None, type=str, choices=['fullscreen', 'multimonitor'])
    parser.add_argument('--width', default=1024, type=int)
    parser.add_argument('--height', default=768, type=int)
    parser.add_argument('--color_bpp', default=32, type=int, choices=[8,15,16,24,32])

    parser.add_argument('--bastion', required=True, type=str)
    parser.add_argument('--user', required=True, type=str)
    parser.add_argument('--password', default=None, type=str)
    parser.add_argument('--filename', required=True, type=str)

    args = parser.parse_args()

    if not args.password:
        password = getpass.getpass(prompt=args.user + "'s password:")
    else:
        password = args.password

    parameters= {}
    parameters['rdp_color_bpp'] = args.color_bpp
    parameters["rdp_resolution"] = args.resolution
    parameters["rdp_width"] = args.width
    parameters["rdp_height"] = args.height

    payload = (args.user, password)
    bastion = args.bastion
    device = args.device
    account = args.account
    domain = args.domain
    filename = args.filename

    with Session() as s:
        s.verify = False
        url = "https://" + bastion + "/api/sessionrights?q={}".format(device)
        r = s.get(url, auth=payload)
        if r and r.status_code == 200:
            body = r.json()
            rights = []
            for right in body:
                if (not account or right['account'] == account) \
                    and (not domain or right['domain'] == domain):
                    rights.append(right)

            if len(rights) != 1:
                 print("error: ambiguous request; matching targets: {:d}".format(len(body)), file=sys.stderr)
                 sys.exit(1)

            right = rights[0]
            if right['type'] != 'device' and device:
                print("error: no matching device", file=sys.stderr)
                sys.exit(1)

            target = get_target(args.user, right)

            generate_rdp_config_file(filename, parameters, target, bastion,
                                    right['subprotocols'], application_cn=None, remoteapp=None)
        else:
            body = r.json()
            print("error:{:d}:{}".format(r.status_code, body['reason']))
            sys.exit(1)

if __name__ == "__main__":
    # execute only if run as a script
    main()