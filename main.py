import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedAudio,
    InlineQueryResultCachedDocument,
    InlineQueryResultCachedGif,
    InlineQueryResultCachedMpeg4Gif,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedSticker,
    InlineQueryResultCachedVideo,
    InlineQueryResultCachedVoice,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputTextMessageContent,
    BotCommand
)
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.bot import DefaultBotProperties
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio
import math
from datetime import datetime
from sticker import add_sticker_to_pack, list_sticker_packs

BOT_TOKEN = "7620694109:AAGwMTjQTnjFC1T7LG25_cLSuR4JB0knscg"
MONGO_URI = "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["file_store_bot"]
files_collection = db["files"]
tags_collection = db["tags"]

class RenameFile(StatesGroup):
    waiting_for_new_name = State()

class AddTag(StatesGroup):
    waiting_for_tags = State()

class TagPagination(StatesGroup):
    selecting_tag = State()

def format_file_size(size_in_bytes):
    if size_in_bytes is None:
        return "Unknown"
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 ** 2:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024 ** 3:
        return f"{size_in_bytes / 1024 ** 2:.2f} MB"
    else:
        return f"{size_in_bytes / 1024 ** 3:.2f} GB"

async def start_cmd(message: Message):
    await message.answer(
        "Send me any file (doc, video, image, etc.) and I’ll store it.\n"
        "You can access them inline by typing <code>@SecureBoxbot</code> in any chat.\n",
        parse_mode="HTML"
    )

async def tags_cmd(message: Message, state: FSMContext):
    user_id = message.from_user.id
    tags_cursor = tags_collection.find({"user_id": user_id}).sort("created_at", -1)
    tags = [doc["tag"] for doc in await tags_cursor.to_list(length=1000)]
    if not tags:
        await message.answer("You don't have any tags yet.")
        return
    await send_tag_page(message, tags, 0, state)

async def send_tag_page(message_or_cb, tags, page, state):
    TAGS_PER_PAGE = 10
    ROWS = 5
    COLS = 2
    total_tags = len(tags)
    start = page * TAGS_PER_PAGE
    end = start + TAGS_PER_PAGE
    page_tags = tags[start:end]

    keyboard = []
    for i in range(0, len(page_tags), COLS):
        row = []
        for tag in page_tags[i:i+COLS]:
            row.append(InlineKeyboardButton(text=tag, callback_data=f"tag_menu:{tag}"))
        keyboard.append(row)
    nav_buttons = []
    max_page = math.ceil(total_tags / TAGS_PER_PAGE) - 1
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"tags_page:{page-1}"))
    if page < max_page:
        nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"tags_page:{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    text = f"Your Tags (Page {page+1}/{max_page+1} | Total: {total_tags}):"
    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=markup)
    elif isinstance(message_or_cb, CallbackQuery):
        if message_or_cb.message:
            await message_or_cb.message.edit_text(text, reply_markup=markup)
        await message_or_cb.answer()

async def save_file(message: Message):
    file_id = None
    file_name = "Unnamed"
    file_size = None
    file_type = None
    message_date = message.date.strftime("%Y-%m-%d %H:%M:%S")

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_size = message.document.file_size
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_name = "video.mp4"
        file_size = message.video.file_size
        file_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
        file_size = message.audio.file_size
        file_type = "audio"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = "photo.jpg"
        file_size = message.photo[-1].file_size
        file_type = "photo"
    elif message.voice:
        file_id = message.voice.file_id
        file_name = "voice.ogg"
        file_size = message.voice.file_size
        file_type = "voice"
    elif message.video_note:
        file_id = message.video_note.file_id
        file_name = "video_note.mp4"
        file_size = message.video_note.file_size
        file_type = "video_note"

    if file_id:
        existing_file = await files_collection.find_one({"file_id": file_id, "user_id": message.from_user.id})
        if existing_file:
            mongo_id = str(existing_file["_id"])
            buttons = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Rename", callback_data=f"rename:{mongo_id}")],
                [InlineKeyboardButton(text="Delete", callback_data=f"delete:{mongo_id}")],
                [InlineKeyboardButton(text="Add Tag", callback_data=f"addtag:{mongo_id}")]
            ])
            await message.reply(
                "This file is already saved in your storage.\n"
                f"File Name: {existing_file['file_name']}\n"
                f"File Type: {existing_file['file_type']}\n"
                f"File Size: {format_file_size(existing_file.get('file_size', 0))}\n"
                f"Message Date: {message_date}",
                reply_markup=buttons
            )
        else:
            result = await files_collection.insert_one({
                "user_id": message.from_user.id,
                "file_id": file_id,
                "file_name": file_name,
                "file_size": file_size,
                "file_type": file_type,
                "tags": [],
                "message_date": message.date
            })
            mongo_id = str(result.inserted_id)
            buttons = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Rename", callback_data=f"rename:{mongo_id}")],
                [InlineKeyboardButton(text="Delete", callback_data=f"delete:{mongo_id}")],
                [InlineKeyboardButton(text="Add Tag", callback_data=f"addtag:{mongo_id}")]
            ])
            await message.reply(
                "File saved successfully!\n"
                f"File Name: {file_name}\n"
                f"File Type: {file_type}\n"
                f"File Size: {format_file_size(file_size)}\n"
                f"Message Date: {message_date}",
                reply_markup=buttons
            )

async def inline_query_handler(inline_query: InlineQuery):
    user_id = inline_query.from_user.id
    query = inline_query.query.lower()
    files_cursor = files_collection.find({"user_id": user_id})
    files = await files_cursor.to_list(length=50)

    results = []
    for f in files:
        file_size_str = format_file_size(f.get("file_size", 0))
        message_date = f.get("message_date")
        tags = f.get("tags", [])
        tags_str = ", ".join(tags) if tags else "No tags"

        if message_date:
            if isinstance(message_date, datetime):
                message_date_str = message_date.strftime("%Y-%m-%d %H:%M:%S")
            else:
                message_date_str = str(message_date)
        else:
            message_date_str = "Unknown"

        if query in f["file_name"].lower() or any(query in tag.lower() for tag in tags):
            file_type = f.get("file_type")
            file_id = f.get("file_id")
            title = f.get("file_name")
            description = f"Type: {file_type.capitalize()} | Size: {file_size_str} | Date: {message_date_str} | Tags: {tags_str}"
            caption = (
                f"File Name: {title}\n"
                f"File Type: {file_type}\n"
                f"File Size: {file_size_str}\n"
                f"Date: {message_date_str}\n"
                f"Tags: {tags_str}"
            )

            try:
                if file_type == "photo":
                    results.append(
                        InlineQueryResultCachedPhoto(
                            id=str(f["_id"]),
                            title=title,
                            photo_file_id=file_id,
                            description=description
                        )
                    )
                elif file_type == "video":
                    results.append(
                        InlineQueryResultCachedVideo(
                            id=str(f["_id"]),
                            title=title,
                            video_file_id=file_id,
                            description=description,
                            caption=caption
                        )
                    )
                elif file_type == "audio":
                    results.append(
                        InlineQueryResultCachedAudio(
                            id=str(f["_id"]),
                            title=title,
                            audio_file_id=file_id,
                            caption=caption
                        )
                    )
                elif file_type == "voice":
                    results.append(
                        InlineQueryResultCachedVoice(
                            id=str(f["_id"]),
                            title=title,
                            voice_file_id=file_id,
                            caption=caption
                        )
                    )
                elif file_type == "sticker":
                    results.append(
                        InlineQueryResultCachedSticker(
                            id=str(f["_id"]),
                            sticker_file_id=file_id
                        )
                    )
                elif file_type == "document" or file_type == "video_note":
                    results.append(
                        InlineQueryResultCachedDocument(
                            id=str(f["_id"]),
                            title=title,
                            document_file_id=file_id,
                            description=description,
                            caption=caption
                        )
                    )
                else:
                    # fallback: unknown types → simple text article
                    results.append(
                        InlineQueryResultArticle(
                            id=str(f["_id"]),
                            title=title,
                            input_message_content=InputTextMessageContent(
                                message_text=caption
                            ),
                            description=description
                        )
                    )
            except Exception as e:
                # Fallback safety: if any error (like bad file_id), send as text article
                results.append(
                    InlineQueryResultArticle(
                        id=str(f["_id"]),
                        title=title,
                        input_message_content=InputTextMessageContent(
                            message_text=f"[Error sending file]\n\n{caption}"
                        ),
                        description=description
                    )
                )

    await bot.answer_inline_query(inline_query.id, results=results, cache_time=0)

async def callback_query_handler(callback_query: CallbackQuery, state: FSMContext):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data.startswith("delete:"):
        file_id = data.split(":", 1)[1]
        try:
            object_id = ObjectId(file_id)
            result = await files_collection.delete_one({"_id": object_id})
            if result.deleted_count > 0:
                if callback_query.message:
                    await callback_query.message.edit_text("The file has been deleted successfully.")
                else:
                    await callback_query.answer("The file has been deleted successfully.", show_alert=True)
            else:
                await callback_query.answer("Failed to delete the file. It may no longer exist.", show_alert=True)
        except Exception as e:
            await callback_query.answer("An error occurred while deleting the file.", show_alert=True)
            logging.error(f"Error deleting file: {e}")

    elif data.startswith("rename:"):
        file_id = data.split(":", 1)[1]
        await state.set_state(RenameFile.waiting_for_new_name)
        await state.update_data(file_id=file_id)
        try:
            await callback_query.message.reply("Please send the new name for the file:")
        except:
            pass
        await callback_query.answer("Please send the new name in this chat.", show_alert=True)

    elif data.startswith("addtag:"):
        file_id = data.split(":", 1)[1]
        await state.set_state(AddTag.waiting_for_tags)
        await state.update_data(file_id=file_id)
        try:
            await callback_query.message.reply("Please send the tag(s) for the file (comma-separated for multiple tags):")
        except:
            pass
        await callback_query.answer("Please send the tag(s) in this chat.", show_alert=True)

    elif data.startswith("tags_page:"):
        page = int(data.split(":", 1)[1])
        tags_cursor = tags_collection.find({"user_id": user_id}).sort("created_at", -1)
        tags = [doc["tag"] for doc in await tags_cursor.to_list(length=1000)]
        await send_tag_page(callback_query, tags, page, state)

    elif data.startswith("tag_menu:"):
        tag = data.split(":", 1)[1]
        keyboard = [
            [InlineKeyboardButton(text="🔎 Inline Search", switch_inline_query_current_chat=tag)],
            [InlineKeyboardButton(text="Rename Tag", callback_data=f"rename_tag_menu:{tag}")],
            [InlineKeyboardButton(text="Delete Tag", callback_data=f"delete_tag_menu:{tag}")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback_query.message.edit_text(
            f"Tag: <b>{tag}</b>\n\nChoose an action:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        await callback_query.answer()

    elif data.startswith("rename_tag_menu:"):
        tag = data.split(":", 1)[1]
        await state.set_state(TagPagination.selecting_tag)
        await state.update_data(tag=tag)
        await callback_query.message.reply(f"Send the new name for the tag <b>{tag}</b>:", parse_mode="HTML")
        await callback_query.answer()

    elif data.startswith("delete_tag_menu:"):
        tag = data.split(":", 1)[1]
        await files_collection.update_many(
            {"user_id": user_id, "tags": tag},
            {"$pull": {"tags": tag}}
        )
        await tags_collection.delete_one({"user_id": user_id, "tag": tag})
        await callback_query.message.edit_text(f"Tag <b>{tag}</b> has been deleted from your files.", parse_mode="HTML")
        await callback_query.answer()

async def rename_file_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = data.get("file_id")
    if not file_id:
        await message.reply("Something went wrong. Try again.")
        return

    new_name = message.text
    object_id = ObjectId(file_id)
    await files_collection.update_one({"_id": object_id}, {"$set": {"file_name": new_name}})
    await message.reply(f"File renamed to: {new_name}")
    await state.clear()

async def tag_reply_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = data.get("file_id")
    if not file_id:
        await message.reply("Something went wrong. Try again.")
        return

    tags = [tag.strip() for tag in message.text.split(",")]
    object_id = ObjectId(file_id)
    await files_collection.update_one({"_id": object_id}, {"$set": {"tags": tags}})
    for tag in tags:
        await tags_collection.update_one(
            {"user_id": message.from_user.id, "tag": tag},
            {"$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )
    await message.reply(f"Tags added: {', '.join(tags)}")
    await state.clear()

async def rename_tag_reply_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    old_tag = data.get("tag")
    user_id = message.from_user.id
    new_tag = message.text.strip()
    if not old_tag or not new_tag:
        await message.reply("Something went wrong. Try again.")
        return
    await files_collection.update_many(
        {"user_id": user_id, "tags": old_tag},
        {"$set": {"tags.$[elem]": new_tag}},
        array_filters=[{"elem": old_tag}]
    )
    tag_doc = await tags_collection.find_one({"user_id": user_id, "tag": old_tag})
    if tag_doc:
        created_at = tag_doc.get("created_at", datetime.utcnow())
        await tags_collection.delete_one({"user_id": user_id, "tag": old_tag})
        await tags_collection.update_one(
            {"user_id": user_id, "tag": new_tag},
            {"$setOnInsert": {"created_at": created_at}},
            upsert=True
        )
    await message.reply(f"Tag <b>{old_tag}</b> renamed to <b>{new_tag}</b>.", parse_mode="HTML")
    await state.clear()

async def sticker_cmd(message: Message):
    await list_sticker_packs(message, db)

async def handle_sticker(message: Message):
    await add_sticker_to_pack(message, bot, db)

async def main():
    logging.basicConfig(level=logging.INFO)
    dp.message.register(start_cmd, Command(commands=["start"]))
    dp.message.register(tags_cmd, Command(commands=["tags"]))
    dp.message.register(sticker_cmd, Command(commands=["sticker"]))
    dp.message.register(save_file, lambda msg: msg.document or msg.video or msg.audio or msg.photo or msg.voice or msg.video_note)
    dp.message.register(rename_file_handler, RenameFile.waiting_for_new_name)
    dp.message.register(tag_reply_handler, AddTag.waiting_for_tags)
    dp.message.register(rename_tag_reply_handler, TagPagination.selecting_tag)
    dp.message.register(handle_sticker, lambda message: message.sticker is not None)
    dp.inline_query.register(inline_query_handler)
    dp.callback_query.register(callback_query_handler)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Start interacting with the bot"),
        BotCommand(command="tags", description="Show your tags"),
        BotCommand(command="sticker", description="View your sticker packs"),
    ])

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
