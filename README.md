# 360ModelSpinner: Automated 3D Model Rendering & Image Processing

![3D Rendering](https://img.shields.io/badge/Blender-3D%20Rendering-blue?logo=blender)
![Python](https://img.shields.io/badge/Python-3.10%2B-green?logo=python)
![License](https://img.shields.io/badge/License-MIT-purple)

Automatically generate professional 360° product renders from 3D models with background removal and optimized image processing. Perfect for e-commerce, product showcases, and 3D asset pipelines.

![Demo](demo.gif)

## ✨ Features

- **360° Automated Rendering**  
  Generates 36 high-quality PNG renders (10° increments) from a single GLB model
- **Smart Scene Setup**  
  Automatic model centering, scaling, lighting, and camera positioning
- **Professional Material Handling**  
  Applies consistent white matte material to all objects
- **Background Removal**  
  Automatic alpha channel processing with smart cropping
- **Optimized Output**  
  Converts renders to standardized JPEG format with neutral background
- **Batch Processing Ready**  
  Designed for integration into automated 3D asset pipelines

## 🛠️ Requirements

### Core System
- Blender 3.0+ ([Download](https://www.blender.org/download/))
- Python 3.10+ (for post-processing)

### Python Dependencies
```bash
pip install pillow
```

## 🚀 Usage

### Step 1: Render 360° Images (Blender)
```bash
blender --background --python render_360.py -- your_model.glb
```
- Input: Any GLB/GLTF 3D model
- Output: 36 PNG files in `renders/` directory (e.g., `your_model_000.png` to `your_model_350.png`)

### Step 2: Process Renders (Python)
```bash
python crop_alpha.py -s renders/your_model_000.png -d output/your_model_000.jpg -w 768 -H 1024
```
*Or process all renders in one command:*
```bash
find . -name "*.png" -exec python crop_alpha.py -s {} -w 768 -H 1152 -d "{}.jpg" -f \;
```

## 📂 Output Structure
```
your_model/
├── renders/
│   ├── your_model_000.png
│   ├── your_model_010.png
│   └── ... (36 total)
└── processed/
    ├── your_model_000.jpg
    ├── your_model_010.jpg
    └── ... (36 total)
```

## ⚙️ Configuration Options

### Rendering Script (`render_360.py`)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_path` | (required) | GLB file path |
| Camera Distance | `max(2.0, max_dim * 1.8)` | Auto-adjusted based on model size |
| Render Resolution | 2048x2048 | PNG with transparency |

### Image Processor (`crop_alpha.py`)
| Flag | Default | Description |
|------|---------|-------------|
| `-w/--width` | 768 | Output width in pixels |
| `-H/--height` | 1024 | Output height in pixels |
| `-f/--force` | false | Overwrite existing files |
| Background | #808080 | Neutral gray background |

## 💡 Workflow Tips

1. **For Product Photography:**
   ```bash
   # Render with tighter camera framing
   blender --python render_360.py -- your_model.glb
   python crop_alpha.py -s renders/ -w 1024 -H 1024
   
   
   ```

2. **For E-commerce:**
   ```bash
   # Create standardized 768x1024 product images
   find renders/ -name "*.png" -exec python crop_alpha.py -s {} -d processed/ -w 768 -H 1024 -f \;
   ```

3. **Custom Material:**
   Modify the material section in `render_360.py` to use your preferred shader:
   ```python
   # Example: Metallic material
   bsdf.inputs['Metallic'].default_value = 0.8
   bsdf.inputs['Roughness'].default_value = 0.2
   ```

## 📜 How It Works

1. **Scene Setup**
   - Clears default scene
   - Imports GLB model
   - Centers model using bounding box calculation
   - Creates rotation pivot point

2. **Rendering Pipeline**
   - Configures 3-point studio lighting
   - Positions camera for optimal framing
   - Applies neutral white material
   - Renders 36 frames (0°-350°)

3. **Image Processing**
   - Crops transparent areas
   - Resizes with aspect ratio preservation
   - Adds neutral background
   - Optimizes for web use

## 🤝 Contributing
Pull requests are welcome! Please:
1. Open an issue for major changes
2. Include tests for new functionality
3. Update documentation

## 📄 License
Distributed under MIT License. See `LICENSE` for details.
