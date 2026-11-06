#!/bin/sh
# Builds and signs DeskDash.apk with Ubuntu's Android packages (see README). Run from the app/ folder.
set -e
cd "$(dirname "$0")"
KS_PASS="${KS_PASS:-deskdash}"
SDK=/usr/lib/android-sdk/platforms/android-23/android.jar
rm -rf build && mkdir -p build/classes build/gen
aapt package -f -m -J build/gen -M AndroidManifest.xml -S res -I $SDK -F build/res.apk --min-sdk-version 19 --target-sdk-version 19
javac -nowarn -Xlint:none -source 8 -target 8 -bootclasspath $SDK -d build/classes build/gen/com/deskdash/R.java src/com/deskdash/*.java 2>&1 | grep -v "warning" || true
dalvik-exchange --dex --min-sdk-version=19 --output=build/classes.dex build/classes
cp build/res.apk build/unsigned.apk
(cd build && cp classes.dex classes.dex.tmp && mv classes.dex.tmp classes.dex && zip -q unsigned.apk classes.dex)
zipalign -f 4 build/unsigned.apk build/aligned.apk
[ -f desk.keystore ] || keytool -genkeypair -keystore desk.keystore -storepass "$KS_PASS" -keypass "$KS_PASS" -alias desk -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Desk Dashboard" 2>/dev/null
apksigner sign --ks desk.keystore --ks-pass "pass:$KS_PASS" --min-sdk-version 19 --out build/DeskDash.apk build/aligned.apk
apksigner verify -v --min-sdk-version 19 build/DeskDash.apk | head -4
ls -l build/DeskDash.apk
