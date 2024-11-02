# bot_app/views.py

import os
import logging
import json  # For parsing JSON data
import asyncio  # For asyncio primitives
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import google.generativeai as genai
import tempfile
from gradio_client import Client
from dotenv import load_dotenv
import json

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

# Initialize the Application
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Flag and Lock for initialization
application_initialized = False
application_lock = asyncio.Lock()


# Helper function to split messages
def split_message(text, max_length):
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]


# Start command handler
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


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_model = query.data
    context.chat_data["selected_model"] = selected_model  # Use chat_data instead

    if selected_model in models:
        await query.edit_message_text(
            f"You selected {selected_model}. Please upload an image for analysis."
        )
    else:
        await query.edit_message_text("Model selection failed!")


# Helper function to upload image to GenAI
async def upload_image_to_genai(file):
    # Create a temporary file
    fd, temp_file_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)  # Close the file descriptor

    try:
        # Download the file from Telegram to the temporary file
        await file.download_to_drive(temp_file_path)

        # Upload the file to GenAI
        sample_file = genai.upload_file(
            path=temp_file_path, display_name="Uploaded Image"
        )
        logging.info(
            f"Uploaded file '{sample_file.display_name}' as: {sample_file.uri}"
        )
        return sample_file
    finally:
        # Clean up: remove the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


import json


def extract_json_from_text(json_string):
    try:
        # Strip the string so that it starts with '{' and ends with '}'
        start_index = json_string.find('{')
        end_index = json_string.rfind('}') + 1

        # If no valid JSON boundaries are found, return None
        if start_index == -1 or end_index == -1:
            return None

        # Extract the portion of the string that starts with '{' and ends with '}'
        json_string = json_string[start_index:end_index]

        # Apply necessary replacements
        cleaned_string = (json_string
                          .replace('\n', '\\n')  # Escape newlines
                          .replace('\\n"', '"')  # Fix comma-newline before string ending
                          .replace('"\\n}', '"}')  # Fix newline before JSON end bracket
                          )

        # Load the cleaned string into a Python object
        json_object = json.loads(cleaned_string)

        # Convert the JSON object back into a pretty-formatted JSON string

        return json_object

    except (json.JSONDecodeError, TypeError) as e:
        # Return None in case of any error
        return None


async def process_images(context, messages, selected_model, chat_id):

    status_message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"Processing your image(s) with the {selected_model} model..."
    )

    # Start a background task to update the status message periodically
    async def update_status():
        dots = 1
        while not getattr(update_status, 'done', False):
            await asyncio.sleep(1)  # Update every 5 seconds
            try:
                await status_message.edit_text(
                    f"Processing your image(s) with the {selected_model} model{'.' * dots}"
                )
                dots = (dots % 7) + 1
            except Exception as e:
                logging.error(f"Error updating status message: {e}")
                break

    status_task = asyncio.create_task(update_status())

    try:
        uploaded_files = []
        for message in messages:
            photos = message.photo
            photo = photos[-1]  # Get the highest resolution photo
            file = await context.bot.get_file(photo.file_id)
            uploaded_file = await upload_image_to_genai(file)
            uploaded_files.append(uploaded_file)

        # Use the GenAI model for analysis
        model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
        prompt = '''Please analyze the image(s) provided and generate a detailed text-based question. This question should include all relevant information visible in the image, such as any text, symbols, and visual context. Ensure the question is fully comprehensive and includes any specific details that could be relevant to solving it, such as edge cases, input formats, and any assumptions that might need to be made based on the image content. The question should be self-contained, meaning that someone (or another AI) reading it should have all the information necessary to answer the question without seeing the image. Your output should be clear and well-structured, ideally in a single paragraph, to facilitate easy understanding and processing by another AI model.



Return the response in the following JSON format:



```

{
 "1": "First question based on the image.",
"2": "Second question based on the image.\\n second line of second question",
"3": "Third question based on the image.",
"...": "..."
}
```
IMPORTANT : the json format should be such that I can directly use json.loads function in python, always use double quots and instead of a single slash for use "\\" example "\\n"

Write exactly what is presented without adding explanations or interpretations. If the image contains multiple questions, clearly separate each one as '1', '2', and so on, ensuring that each question is distinct and correctly formatted in the JSON structure.'''

        # Run the blocking call in a separate thread
        response = await asyncio.to_thread(model.generate_content, [prompt] + uploaded_files)
        gemini_output = response.text  # Adjust according to actual response format

        json_questions = extract_json_from_text(gemini_output)


        if json_questions is None:
            # Handle the case where JSON extraction failed
            await context.bot.send_message(
                chat_id=chat_id,
                text="Failed to extract questions from the image analysis. Please try again." + gemini_output
            )
            await status_message.edit_text("Processing complete.")
            return

        for question_number, question_text in json_questions.items():
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"EXTRACTED QEUSTIONS: {question_number} : {question_text}"
            )
        # Iterate over the questions
        for question_number, question_text in json_questions.items():
            models_to_try = [m for m in models.keys() if m != selected_model]
            models_to_try.insert(0, selected_model)  # Ensure selected model is tried first



            for model_name in models_to_try:
                try:

                    client = Client(f"yuntian-deng/{model_name}")
                    # Create the prompt for the question
                    inputs = f'''Deliver your answer clearly and concisely:

                        1. **For multiple-choice questions (MCQs)**, only provide the correct option number and option value(e.g., **"Answer: B <option value>"**) without any additional explanation unless specified.
                        
                        2. **For questions involving code**, use C++ and format your code clearly. Encapsulate code segments using triple backticks (```) to enhance readability.
                        
                        3. **For non-code questions** that require explanations, provide a straightforward answer give code block only if needed.
                        
                        Answer the question in a format that is precise, directly addresses the specifics, and is easy to read in a Telegram message.
                        
                        Question {question_number}: {question_text}'''

                    # Run client.predict with the inputs
                    result = await asyncio.to_thread(
                        client.predict,
                        inputs=inputs,
                        top_p=0.9,
                        temperature=0.5,
                        chat_counter=0,
                        chatbot=[],
                        api_name="/predict",
                    )

                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"{question_number} : {question_text} done using {model_name}"
                    )

                    message_text = result[0][0][1]  # Adjust according to actual response format

                    # Send the result back to the user
                    message_chunks = split_message(message_text, MAX_MESSAGE_LENGTH)
                    for chunk in message_chunks:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=chunk,
                            parse_mode='Markdown'
                        )

                    # Update the status message
                    await status_message.edit_text(f"Processed question {question_number} successfully.")
                    # Break out of the models_to_try loop since we have successfully processed the question

                    break


                except Exception as e:
                    logging.error(f"Error processing question {question_number} with {model_name}: {e}")
                    # Optionally, inform user of fallback
                    await status_message.edit_text(
                        f"There was an issue processing question {question_number} with {model_name}. Trying with the next fallback model..."
                    )
                    # Continue to next model

            else:
                # If all models fail for this question, send a message to the user
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"All models failed to process question {question_number}. Please try again later."
                )

        # After all questions are processed, edit the status message
        await status_message.edit_text("Processing complete.")

    finally:
        update_status.done = True
        await status_task

        # Inform the user that they need to start over
        await context.bot.send_message(
            chat_id=chat_id,
            text="Processing complete. "
        )


# Function to handle image uploads
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == context.bot.id:
        logging.info("Ignoring message from the bot itself.")
        return

    if update.message.from_user and update.message.from_user.is_bot:
        return

    if "selected_model" not in context.chat_data:  # Use chat_data here
        await update.message.reply_text(
            "Please select a model first using the /start command."
        )
        return

    selected_model = context.chat_data["selected_model"]  # And here

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

        context.chat_data['media_groups'][media_group_id].append(update.message)


        if media_group_id in context.chat_data['media_group_jobs']:
            context.chat_data['media_group_jobs'][media_group_id].schedule_removal()

        # Schedule a new job to process this media group after 2 seconds
        job = context.application.job_queue.run_once(
            process_media_group,
            when=2,  # seconds
            data={
                'media_group_id': media_group_id,
                'selected_model': selected_model,
                'chat_id': chat_id,
            },
            user_id=update.effective_user.id,
            chat_id=chat_id,
        )
        # Store the job so we can cancel/reschedule it if needed
        context.chat_data['media_group_jobs'][media_group_id] = job
    else:

        await process_images(
            context, [update.message], selected_model, chat_id
        )


# Function to process media group after waiting
async def process_media_group(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    job_data = job.data
    media_group_id = job_data['media_group_id']
    selected_model = job_data['selected_model']
    chat_id = job_data['chat_id']

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


# Webhook view to receive updates from Telegram
@csrf_exempt
async def webhook(request):
    global application_initialized
    if not application_initialized:
        # Ensure that only one coroutine initializes the application
        async with application_lock:
            if not application_initialized:
                await application.initialize()
                application.job_queue.scheduler.start()
                application_initialized = True

    if request.method == 'POST':
        # Retrieve the JSON update from Telegram
        request_body = request.body  # Do not await request.body
        try:
            data = json.loads(request_body.decode('utf-8'))  # Parse JSON data
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON: {e}")
            return HttpResponse(status=400)  # Return 400 Bad Request if JSON is invalid

        # Parse the JSON data into an Update object
        update = Update.de_json(data, application.bot)

        # Process the update with the application
        asyncio.create_task(application.process_update(update))
        return HttpResponse(status=200)
    else:
        return HttpResponse("Hello, world. This is the bot webhook endpoint.")


# Register handlers with the application
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))

application.add_handler(MessageHandler(filters.PHOTO, handle_image))




