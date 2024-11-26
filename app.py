import gradio as gr
import requests
import io
import tempfile
from PIL import Image, ImageOps
import base64
import time
import json


def generate_and_download_image():
    image = Image.new("RGB", (256, 256), color=(255, 0, 0))

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)  


    return img_byte_arr, "generated_composite_image.png"

def load_image_from_url(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        return image,image,image
    except Exception as e:
        return None, f"Error: {e}"

def send_to_api(key, prompt, image_url, mask_url, path_points):
    """Send the image and mask to the API endpoint."""

    path_points = path_points.replace("'", '"')
    path_points_list = json.loads(path_points) 

    url = "https://api.goapi.ai/api/v1/task"
    payload = {
        "model": "kling",
        "task_type": "video_generation",
        "input": {
            "prompt": prompt,
            "negative_prompt": "",
            "cfg_scale": 0.5,
            "duration": 5,
            "image_url": image_url, 
            "image_tail_url": "",
            "mode": "std",
            "version": "1.0",
            "motion_brush": {
                "mask_url": mask_url, 
                "static_masks": [{"points": []}],
                "dynamic_masks": [{"points": path_points_list}]
            }
        }
    }

    headers = {
        "x-api-key": key  
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        task_id = data.get("data", {}).get("task_id")  
        return task_id if task_id else None
    else:
        return f"Request failed, status code: {response.status_code}", None

def fetch_api(task_id, key):
    """Fetch task status and return video URL, retrying every 10 seconds until task is completed."""
    url = f"https://api.goapi.ai/api/v1/task/{task_id}"
    headers = {
        "x-api-key": key
    }

    while True:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            status = data.get("data", {}).get("status", "")
            if status == "completed":
                video_url = data.get("data", {}).get("output", {}).get("video_url", "Error video URL")
                return video_url
            if status == "failed":
                video_url = data.get("data", {}).get("output", {}).get("video_url", "Error video URL")
                return ""
            
            else:
                print(f"Task status is '{status}'. Retrying in 10 seconds...")
        else:
            return f"Request failed, status code: {response.status_code}", None
        
        time.sleep(10)

def image_to_base64(image):
    """Convert a PIL Image to a base64-encoded PNG string."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_base64

def generate_mask_and_path(dynamic_mask_value, static_mask_value, path_points_value, path_direction):

    dynamic_mask_layers = dynamic_mask_value.get("layers", [])
    static_mask_layers = static_mask_value.get("layers", [])
    path_points_layers = path_points_value.get("layers", [])


    green_layer = dynamic_mask_layers[0]
    green_rgb = (114, 229, 40)
  
    green_mask = ImageOps.colorize(
      ImageOps.grayscale(green_layer), black="black", white=green_rgb
    )   

    black_layer = static_mask_layers[0]
    black_mask = ImageOps.colorize(
        ImageOps.grayscale(green_layer), black="black", white="green"
    )

    width, height = green_mask.size
    composite_image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    composite_image.paste(green_mask, mask=green_layer)
    composite_image.paste(black_mask, mask=black_layer)

    path_layer = path_points_layers[0]
    path_array = path_layer.load()
    path_points = []

    # Generate path points based on selected direction
    if path_direction == "Left to Right":
        for y in range(height):
            for x in range(width):
                if path_array[x, y] == (255, 255, 255, 255):
                    path_points.append({"x": x, "y": y})
        path_points.sort(key=lambda point: (point['x'], point['y']))
    elif path_direction == "Right to Left":
        for y in range(height):
            for x in range(width - 1, -1, -1):
                if path_array[x, y] == (255, 255, 255, 255):
                    path_points.append({"x": x, "y": y})
        path_points.sort(key=lambda point: (point['x'], point['y']), reverse=True)
    elif path_direction == "Top to Bottom":
        for x in range(width):
            for y in range(height):
                if path_array[x, y] == (255, 255, 255, 255):
                    path_points.append({"x": x, "y": y})
        path_points.sort(key=lambda point: (point['y'], point['x']))
    elif path_direction == "Bottom to Top":
        for x in range(width):
            for y in range(height - 1, -1, -1):
                if path_array[x, y] == (255, 255, 255, 255):
                    path_points.append({"x": x, "y": y})
        path_points.sort(key=lambda point: (point['y'], point['x']), reverse=True)

    
    selected_points = []

    if path_points:
        step = max(len(path_points) // 20, 1)  
        selected_points = []

        selected_points.append(path_points[0])

        for i in range(1, len(path_points) - 1, step):
          avg_x = sum(point['x'] for point in path_points[i:i+step]) // len(path_points[i:i+step])
          avg_y = sum(point['y'] for point in path_points[i:i+step]) // len(path_points[i:i+step])
          selected_points.append({"x": avg_x, "y": avg_y})


        print(path_points[-1])
        selected_points.append(path_points[-1])


    img_byte_arr = io.BytesIO()
    composite_image.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0) 

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    with open(temp_file.name, "wb") as f:
       f.write(img_byte_arr.read())

    return temp_file.name, selected_points

def generate_video(key, prompt,mask_url, original_image_url,path_points):
    task_id = send_to_api(key, prompt, original_image_url, mask_url, path_points)
    video_url = fetch_api(task_id, key)

    return task_id, video_url


with gr.Blocks() as interface:
    gr.Markdown("# Video Motion Generation Tool")

    gr.Markdown("---")
    gr.Markdown("### 1. Input Background Image URL")
    with gr.Row():
        url_input = gr.Textbox(label="Input Background Image URL", placeholder="Enter the image URL",value="https://i.ibb.co/VBdYTJC/301649-20200826221337967.jpg" )
        load_image_btn = gr.Button("Load Image")

    gr.Markdown("---")
    gr.Markdown("### 2. Brush Tool for Editing Image")

    gr.Markdown("#### 2.1 Dynamic Mask (Required): This mask will generate movement effects.")
    gr.Markdown("In this step, draw on **Layer 1** of imagEedit to create the dynamic mask.")

    with gr.Row():
        dynamic_mask_editor = gr.ImageEditor(
            type="pil",
            brush=gr.Brush(default_size=20, colors=["#FFFFFF"], color_mode="fixed"),
            layers=True,  
            interactive=True,
            label="Drawing Tool to Create Dynamic Mask (Layer 1)",
            height=700,
        )


    gr.Markdown("#### 2.2 Static Mask (Optional): This mask will remain still during the video.")
    gr.Markdown("You can optionally draw on **Layer 1** of imagEedit to create the static mask.")

    with gr.Row():
        static_mask_editor = gr.ImageEditor(
            type="pil",
            brush=gr.Brush(default_size=20, colors=["#FFFFFF"], color_mode="fixed"),
            layers=True,  
            interactive=True,
            label="Drawing Tool to Create Static Mask (Layer 1)",
            height=700,
        )


    gr.Markdown("#### 2.3 Path Points (Required): These points define the direction and flow of the animation.")
    gr.Markdown("Draw on **Layer 1** of imagEedit to create the path points.")

    with gr.Row():
        path_points_editor = gr.ImageEditor(
            type="pil",
            brush=gr.Brush(default_size=1, colors=["#FFFFFF"], color_mode="fixed"),
            layers=True,  
            interactive=True,
            label="Drawing Tool to Create Path Points (Layer 1)",
            height=700,
        )

    with gr.Row():
        direction_input = gr.Dropdown(
            choices=["Left to Right", "Right to Left", "Top to Bottom", "Bottom to Top"], 
            label="Select Path Direction"
        )

    submit_btn = gr.Button("Generate masks and paths")

    gr.Markdown("Upload the downloaded mask image to a public image hosting service (e.g., [ImageBB](https://imgbb.com/)) and paste the provided link into the `mask_url` field.")
    with gr.Row():
        output_composite_file = gr.File(label="Generated Composite Image")
        output_path_points = gr.Textbox(label="Path Point Data")


    gr.Markdown("---")
    gr.Markdown("### 3. Configure the Video Settings")
    gr.Markdown("Please provide the necessary details to generate the video. If you don't have an API key, you can [generate one here](https://piapi.ai/workspace/kling).")

    with gr.Row():
        prompt_input = gr.Textbox(label="Prompt", placeholder="Enter Prompt",value="walk")

    
    with gr.Row():
        key_input = gr.Textbox(label="API Key", placeholder="Enter PiAPI Key")

    with gr.Row():
        mask_input = gr.Textbox(label="Mask Url")
    
    with gr.Row():
        generate_btn = gr.Button("Generate Video")

    gr.Markdown("---")
    gr.Markdown("### 4. Results")
    gr.Markdown("The video generation may take up to **3 minutes**. Please be patient while the system processes the request.")
    with gr.Row():
        output_task_id = gr.Textbox(label="Task ID")
        output_video = gr.Video(label="Generated Video Link")


    load_image_btn.click(
        fn=load_image_from_url,
        inputs=[url_input],
        outputs=[dynamic_mask_editor,static_mask_editor,path_points_editor],
    )

   
    submit_btn.click(
        fn=generate_mask_and_path,
        inputs=[dynamic_mask_editor, static_mask_editor, path_points_editor, direction_input],
        outputs=[output_composite_file, output_path_points],
    )

 
    generate_btn.click(
        fn=generate_video,
        inputs=[key_input, prompt_input,mask_input, url_input,output_path_points],
        outputs=[output_task_id, output_video],
    )
    

interface.launch()

