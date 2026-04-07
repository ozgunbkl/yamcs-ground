# Yamcs QuickStart

This repository holds the source code to start a basic Yamcs application that monitors a simulated spacecraft in low earth orbit.

You may find it useful as a starting point for your own project.


## Prerequisites

* Java 17+
* Linux x64/aarch64, macOS x64/aarch64, or Windows x64

A copy of Maven is also required, however this gets automatically downloaded an installed by using the `./mvnw` shell script as detailed below.


## Running Yamcs

Here are some commands to get things started:

Compile this project:

    ./mvnw compile

Start Yamcs on localhost:

    ./mvnw yamcs:run

Same as yamcs:run, but allows a debugger to attach at port 7896:

    ./mvnw yamcs:debug
    
Delete all generated outputs and start over:

    ./mvnw clean

This will also delete Yamcs data. Change the `dataDir` property in `yamcs.yaml` to another location on your file system if you don't want that.


## Telemetry

To start pushing CCSDS packets into Yamcs, run the included Python script:

    python simulator.py

This script will send packets at 1 Hz over UDP to Yamcs. There is enough test data to run for a full calendar day.

The packets are a bit artificial and include a mixture of HK and accessory data.

## Real ESP32 FSW Telemetry (Wi-Fi)

To receive live telemetry from ESP32 flight software instead of simulator.py:

1. Start Yamcs:

    mvnw.cmd yamcs:run

2. Open Yamcs web UI:

    http://localhost:8090

3. In the ESP32 project, set the destination IP to your PC IPv4 address on the same Wi-Fi network:

    components/comms/yamcs_interface.h

   Update YAMCS_DEST_IP from the placeholder value to your actual PC IP.

4. In the ESP32 project, set your Wi-Fi credentials in main/main.c:

   - WIFI_SSID
   - WIFI_PASSWORD

5. Flash and run ESP32 firmware. Keep USB connected for flashing/logs, while telemetry transport uses Wi-Fi UDP.

6. Do not run simulator.py when testing real hardware telemetry.


## Telecommanding

This project defines a few example CCSDS telecommands. They are sent to UDP port 10025. The simulator.py script listens to this port. Commands  have no side effects. The script will only count them.


## Bundling

Running through Maven is useful during development, but it is not recommended for production environments. Instead bundle up your Yamcs application in a tar.gz file:

    ./mvnw package
