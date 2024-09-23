import logging
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext,
)
import google.generativeai as genai
from dotenv import load_dotenv
import tempfile
from gradio_client import Client
MAX_MESSAGE_LENGTH = 4000

# Load environment variables from .env file
load_dotenv()

# Fetch API keys from environment variables
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Configure the Google GenAI API with the provided key.
genai.configure(api_key=GOOGLE_API_KEY)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# List of models
models = {
    "o1": "o1",
    "o1mini": "o1mini",
    "ChatGPT4": "ChatGPT4",
}

# Function to handle /start command and show model selection

def split_message(text, max_length):
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Use o1", callback_data="o1")],
        [InlineKeyboardButton("Use o1mini", callback_data="o1mini")],
        [InlineKeyboardButton("Use ChatGPT4", callback_data="ChatGPT4")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Choose the model you want to use to process the image analysis output:",
        reply_markup=reply_markup,
    )

# Function to handle model selection
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_model = query.data
    context.user_data["selected_model"] = selected_model

    if selected_model in models:
        await query.edit_message_text(
            f"You selected {selected_model}. Please upload an image for analysis."
        )
    else:
        await query.edit_message_text("Model selection failed!")

# Helper function to handle image file upload to GenAI
async def upload_image_to_genai(file):
    # Create a temporary file and close it immediately
    fd, temp_file_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)  # Close the file descriptor to prevent the file from being held open

    try:
        await file.download_to_drive(temp_file_path)

        # Upload the file to GenAI using the temporary file path
        sample_file = genai.upload_file(
            path=temp_file_path, display_name="Uploaded Image"
        )
        logging.info(
            f"Uploaded file '{sample_file.display_name}' as: {sample_file.uri}"
        )
        return sample_file
    finally:
        # Clean up: remove the temporary file after the operation
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

# Function to process images (single or multiple)
async def process_images(context, messages, selected_model, chat_id):
    # Send status message to the user
    status_message = await context.bot.send_message(
        chat_id=chat_id,
        text="Processing your image(s) with the Gemini model..."
    )

    uploaded_files = []
    for message in messages:
        photos = message.photo
        photo = photos[-1]  # Get the highest resolution photo
        file = await context.bot.get_file(photo.file_id)
        uploaded_file = await upload_image_to_genai(file)
        uploaded_files.append(uploaded_file)

    # Use the Gemini model for analysis
    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    prompt = "return whatever is written in the image,basically perform ocr of all images"
    response = model.generate_content([prompt] + uploaded_files)
    gemini_output = response.text  # Adjust according to actual response format
    print(gemini_output)
    # Update status message
    await status_message.edit_text(
        f"Processing the Gemini output with the {selected_model} model..."
    )

    # Use Gradio client to process the Gemini output with the selected model
    client = Client(f"yuntian-deng/{selected_model}")
    result = client.predict(
        inputs=gemini_output + "explain whatever is written",
        top_p=1,
        temperature=1,
        chat_counter=0,
        chatbot=[],
        api_name="/predict",
    )
    message_text = result[0][0][1]  # Limit the message text to the first 4000 characters
    # Send the final result back to the user
    message_chunks = split_message(message_text, MAX_MESSAGE_LENGTH)

    # Send each chunk as a separate message
    for chunk in message_chunks:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Final Result from {selected_model} model:\n{chunk}",
        )


# Function to handle image uploads
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "selected_model" not in context.user_data:
        await update.message.reply_text(
            "Please select a model first using the /start command."
        )
        return

    selected_model = context.user_data["selected_model"]

    chat_id = update.effective_chat.id

    # Initialize media_groups and media_group_jobs in context.chat_data if not present
    if 'media_groups' not in context.chat_data:
        context.chat_data['media_groups'] = {}
    if 'media_group_jobs' not in context.chat_data:
        context.chat_data['media_group_jobs'] = {}

    media_group_id = update.message.media_group_id

    if media_group_id:
        # This message is part of a media group
        if media_group_id not in context.chat_data['media_groups']:
            context.chat_data['media_groups'][media_group_id] = []
        # Store the message
        context.chat_data['media_groups'][media_group_id].append(update.message)

        # Cancel any existing job for this media_group_id
        if media_group_id in context.chat_data['media_group_jobs']:
            context.chat_data['media_group_jobs'][media_group_id].schedule_removal()

        # Schedule a new job to process this media group after 2 seconds
        job = context.application.job_queue.run_once(
            process_media_group,
            when=2,  # seconds
            chat_id=chat_id,
            data={
                'media_group_id': media_group_id,
                'selected_model': selected_model,
            }
        )
        # Store the job so we can cancel/reschedule it if needed
        context.chat_data['media_group_jobs'][media_group_id] = job
    else:
        # Single image, process it immediately
        await process_images(
            context, [update.message], selected_model, update.effective_chat.id
        )

# Function to process media group after waiting
async def process_media_group(context: CallbackContext):
    job_data = context.job.data
    media_group_id = job_data['media_group_id']
    selected_model = job_data['selected_model']
    chat_id = context.job.chat_id

    # Retrieve the stored messages (photos)
    chat_data = context.application.chat_data.get(chat_id, {})
    media_groups = chat_data.get('media_groups', {})
    messages = media_groups.pop(media_group_id, [])

    # Remove the job from media_group_jobs
    media_group_jobs = chat_data.get('media_group_jobs', {})
    media_group_jobs.pop(media_group_id, None)

    if messages:
        await process_images(
            context, messages, selected_model, chat_id=chat_id
        )

# Main function to run the bot
if __name__ == "__main__":
    # Ensure that the environment variables are set
    if not GOOGLE_API_KEY or not TELEGRAM_BOT_TOKEN:
        raise EnvironmentError(
            "GOOGLE_API_KEY or TELEGRAM_BOT_TOKEN is not set in the environment."
        )

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Command to start the bot and show model selection
    application.add_handler(CommandHandler("start", start))

    # CallbackQueryHandler to handle button clicks for model selection
    application.add_handler(CallbackQueryHandler(button_handler))

    # Handler for image uploads
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))

    application.run_polling()
