#!/bin/bash

set -e

echo "Downloading LiveKit CLI..."

ARCH=$(dpkg --print-architecture)

LK_VERSION="1.4.0"

DOWNLOAD_URL="https://github.com/livekit/livekit-cli/releases/download/v${LK_VERSION}/lk_Linux_${ARCH}"

curl -L ${DOWNLOAD_URL} -o lk

chmod +x lk

mkdir -p bin
mv lk bin/

echo "LiveKit CLI installed successfully to ./bin/lk"
