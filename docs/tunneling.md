Certainly! Here's an updated and clearer version of the documentation in English, emphasizing how to set the `tunnel_type`:

# 🚀 Pulsar Tunneling Configuration Guide

## 🔧 Where to Configure

Edit the `last.yaml` configuration file, typically located at:

- 🐧 Linux/Mac: `~/pulsar/configs`
- 🪟 Windows: `%userprofile%\pulsar\configs`

## 🚇 Setting the Tunnel Type

In the `last.yaml` file, find or add the `tunnel_type` line. Set this parameter using one of the following values:


`tunnel_type: 'sish'    # 🌟 Recommended option`


OR

`tunnel_type: 'localtunnel'`

OR

`tunnel_type: 'ngrok'`

OR 

`tunnel_type: 'serveo'  # 🚫 Currently disabled`

OR 

`tunnel_type: 'local_ip'`

OR 

`tunnel_type: 'no_tunnel' # 🔄 Disables tunneling`

OR

`tunnel_type: null      # 🔄 Default behavior`

## 📋 Option Details

1. 🌟 **'sish'** (Recommended)
   - Self-hosted solution
   - Most reliable option

2. 🌐 **'localtunnel'**
   - Third-party service

3. 🔗 **'ngrok'**
   - Popular tunneling service

4. 🚫 **'serveo'** (Currently Disabled)
   - Experiencing frequent downtimes

5. 🏠 **'local_ip'**
   - Uses your local network IP
   - Allows connections within your local network

6. 🔄 **'no_tunnel'**
   - Disables tunneling

## 💡 Tips

- Choose the tunnel type that best suits your needs
- 'sish' is recommended for better reliability
- 'local_ip' is ideal for home network setups
- If you don't set a `tunnel_type`, clients will automatically use try iterating through [sish, localtunnel, ngrok] in that order

Need more help? Don't hesitate to reach out to your friendly Pulsar support team! 😊
