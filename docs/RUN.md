find .  -maxdepth 1 -type f \( -iname "*.glb" \) -exec sh -c 'for f; do dir=$(dirname "$f"); ext=$(echo "${f##*.}" | tr "[:upper:]" "[:lower:]"); hash=$(md5 -q "$f"); mv "$f" "$dir/$hash.$ext"; done' _ {} +


/Applications/Blender.app/Contents/MacOS/Blender \
--background \
--python "/Users/user/PycharmProjects/360ModelSpinner/src/cli/render_360_directory.py" \
-- "/Users/user/Downloads/GLB0 (5).glb"

find /Users/user/Downloads/renders -type f -name "*.png" -exec bash -c 'python /Users/user/Documents/3DToImage/crop_alpha.py -s "$0" -w 640 -H 1024 -f' {} \;


python /Users/user/PycharmProjects/360ModelSpinner/src/cli/image_similarity_search.py --images . --find-unique --copy-unique-to ./unique_photos


python3 /Users/user/PycharmProjects/360ModelSpinner/src/cli/crop_alpha.py -i . -p SIZE_896x1200

/Applications/Blender.app/Contents/MacOS/Blender \
--background \
--python "/Users/user/PycharmProjects/360ModelSpinner/src/cli/render_360_directory_camera_angles.py" \
-- "/Users/user/Downloads/ZlA8EKU11AzU59npPvTXc.stl"

/Applications/Blender.app/Contents/MacOS/Blender \
--background \
--python "/Users/user/PycharmProjects/360ModelSpinner/src/cli/render_360_controlnet.py" \
-- "/Users/user/Downloads/Untitled123.stl"


/Applications/Blender.app/Contents/MacOS/Blender --background \
    --python /Users/user/PycharmProjects/360ModelSpinner/src/cli/compositor_edges.py -- \
    -i "/Users/user/Downloads/1381b9dcd74269f13d6005122548005e.stl" \
    -o ./output_compositor.png \
    -r 1024