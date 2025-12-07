/Applications/Blender.app/Contents/MacOS/Blender \
--background \
--python "/Users/user/PycharmProjects/360ModelSpinner/src/cli/render_360_directory.py" \
-- "/Users/user/Downloads/c113ba5f038507ae995276047c68986d.glb"

find /Users/user/Downloads/renders/set_001 -type f -name "*.png" -exec bash -c 'python /Users/user/Documents/3DToImage/crop_alpha.py -s "$0" -w 768 -H 1024 -f' {} \;