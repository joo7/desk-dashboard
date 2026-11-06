#!/bin/sh
# Builds and signs DeskDash.apk with Ubuntu's Android packages (see README). Can be run from anywhere.
# Set SDK to use an android.jar from another location.
set -e
cd "$(dirname "$0")"
KS_PASS="${KS_PASS:-deskdash}"
SDK="${SDK:-/usr/lib/android-sdk/platforms/android-23/android.jar}"

# Conscrypt: modern TLS library. Android 4.4's own TLS cannot talk to today's servers (no AES-GCM or ChaCha20).
# 2.5.3 is the newest release that still supports Android 4.4. Downloaded once, checked against this hash.
CONSCRYPT=2.5.3
CONSCRYPT_SHA256=551ae4e301c571760d1791e647db6ed1dcb10d34dcae7aa12b67f220f2ce98d1
AAR="libs/conscrypt-android-$CONSCRYPT.aar"
if [ ! -f "$AAR" ]; then
  mkdir -p libs
  curl -fsSL -o "$AAR.part" "https://repo1.maven.org/maven2/org/conscrypt/conscrypt-android/$CONSCRYPT/conscrypt-android-$CONSCRYPT.aar"
  mv "$AAR.part" "$AAR"
fi
echo "$CONSCRYPT_SHA256  $AAR" | sha256sum -c --quiet -

rm -rf build && mkdir -p build/classes build/gen build/conscrypt
unzip -q "$AAR" classes.jar 'jni/armeabi-v7a/*' -d build/conscrypt
aapt package -f -m -J build/gen -M AndroidManifest.xml -S res -I "$SDK" -F build/res.apk --min-sdk-version 19 --target-sdk-version 19
javac -nowarn -Xlint:-options -source 8 -target 8 -bootclasspath "$SDK" -cp build/conscrypt/classes.jar -d build/classes build/gen/com/deskdash/R.java src/com/deskdash/*.java
dalvik-exchange --dex --min-sdk-version=19 --output=build/classes.dex build/classes build/conscrypt/classes.jar
cp build/res.apk build/unsigned.apk
mkdir -p build/apk/lib && cp -r build/conscrypt/jni/armeabi-v7a build/apk/lib/
(cd build && zip -q unsigned.apk classes.dex && cd apk && zip -qr ../unsigned.apk lib)
zipalign -f 4 build/unsigned.apk build/aligned.apk
[ -f desk.keystore ] || keytool -genkeypair -keystore desk.keystore -storepass "$KS_PASS" -keypass "$KS_PASS" -alias desk -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Desk Dashboard" 2>/dev/null
apksigner sign --ks desk.keystore --ks-pass "pass:$KS_PASS" --min-sdk-version 19 --out build/DeskDash.apk build/aligned.apk
apksigner verify -v --min-sdk-version 19 build/DeskDash.apk | head -4
ls -l build/DeskDash.apk
