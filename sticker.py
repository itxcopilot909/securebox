import logging
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputSticker
from aiogram.exceptions import TelegramAPIError
from datetime import datetime

PACK_SUFFIX = "_by_whatsisbot"  # Replace with your bot's username if needed

def get_sticker_type(sticker):
    if getattr(sticker, 'is_video', False):
        return "video"
    if getattr(sticker, 'is_animated', False):
        return "animated"
    return "static"

def get_sticker_pack_name(user_id, sticker_type, index=1):
    return f"user{user_id}_{sticker_type}_{index}{PACK_SUFFIX}"

async def ensure_sticker_pack(bot, db, user_id, user_name, sticker_type, title, first_sticker_file_id, emoji, index=1):
    packs_collection = db["sticker_packs"]
    pack_name = get_sticker_pack_name(user_id, sticker_type, index)
    sticker_set_title = f"{user_name}'s {sticker_type.capitalize()} Stickers {index}"

    try:
        input_sticker = InputSticker(
            sticker=first_sticker_file_id,
            format=sticker_type,
            emoji_list=[emoji]
        )
        await bot.create_new_sticker_set(
            user_id=user_id,
            name=pack_name,
            title=sticker_set_title,
            stickers=[input_sticker]
        )
        await packs_collection.insert_one({
            "user_id": user_id,
            "sticker_type": sticker_type,
            "name": pack_name,
            "index": index,
            "created_at": datetime.utcnow(),
            "deleted": False
        })
        return pack_name, index
    except TelegramAPIError as e:
        logging.error(f"Error creating sticker pack: {e}")
        raise

async def add_sticker_to_pack(message: Message, bot: Bot, db):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    stickers_collection = db["stickers"]
    packs_collection = db["sticker_packs"]

    sticker = message.sticker
    sticker_type = get_sticker_type(sticker)
    file_unique_id = sticker.file_unique_id
    emoji = sticker.emoji or "😄"

    # Check for duplicates
    exists = await stickers_collection.find_one({
        "user_id": user_id,
        "file_unique_id": file_unique_id,
        "sticker_type": sticker_type
    })
    if exists:
        await message.reply("This sticker is already in your pack. Duplicate skipped.")
        return

    # Find the latest non-deleted pack of the correct type
    pack_doc = await packs_collection.find_one(
        {
            "user_id": user_id,
            "sticker_type": sticker_type,
            "deleted": {"$ne": True}
        },
        sort=[("index", -1)]
    )

    if pack_doc:
        pack_name = pack_doc["name"]
        index = pack_doc["index"]
        try:
            input_sticker = InputSticker(
                sticker=sticker.file_id,
                format=sticker_type,
                emoji_list=[emoji]
            )
            await bot.add_sticker_to_set(
                user_id=user_id,
                name=pack_name,
                sticker=input_sticker
            )
        except TelegramAPIError as e:
            error_str = str(e)
            if (
                "Stickers set is full" in error_str
                or "STICKERSET_INVALID" in error_str
            ):
                # Mark this pack as deleted
                await packs_collection.update_one(
                    {"user_id": user_id, "name": pack_name, "sticker_type": sticker_type},
                    {"$set": {"deleted": True}}
                )
                # Find next index
                last_pack = await packs_collection.find_one(
                    {"user_id": user_id, "sticker_type": sticker_type},
                    sort=[("index", -1)]
                )
                next_index = (last_pack["index"] if last_pack else 0) + 1
                pack_name, _ = await ensure_sticker_pack(
                    bot, db, user_id, user_name, sticker_type,
                    title=f"{user_name}'s {sticker_type.capitalize()} Stickers {next_index}",
                    first_sticker_file_id=sticker.file_id,
                    emoji=emoji,
                    index=next_index
                )
                await stickers_collection.insert_one({
                    "user_id": user_id,
                    "file_unique_id": file_unique_id,
                    "file_id": sticker.file_id,
                    "emoji": emoji,
                    "sticker_type": sticker_type,
                    "pack_name": pack_name,
                    "added_at": datetime.utcnow()
                })
                await message.reply(
                    f"Sticker added to your new {sticker_type} pack!\n"
                    f"<a href='https://t.me/addstickers/{pack_name}'>Open pack</a>",
                    parse_mode="HTML"
                )
                return
            else:
                await message.reply("Failed to add sticker: " + error_str)
                return

        # Success, record in DB
        await stickers_collection.insert_one({
            "user_id": user_id,
            "file_unique_id": file_unique_id,
            "file_id": sticker.file_id,
            "emoji": emoji,
            "sticker_type": sticker_type,
            "pack_name": pack_name,
            "added_at": datetime.utcnow()
        })
        await message.reply(
            f"Sticker added to your {sticker_type} pack!\n"
            f"<a href='https://t.me/addstickers/{pack_name}'>Open pack</a>",
            parse_mode="HTML"
        )
    else:
        # No pack exists, create one
        last_pack = await packs_collection.find_one(
            {"user_id": user_id, "sticker_type": sticker_type},
            sort=[("index", -1)]
        )
        next_index = (last_pack["index"] if last_pack else 0) + 1
        pack_name, _ = await ensure_sticker_pack(
            bot, db, user_id, user_name, sticker_type,
            title=f"{user_name}'s {sticker_type.capitalize()} Stickers {next_index}",
            first_sticker_file_id=sticker.file_id,
            emoji=emoji,
            index=next_index
        )
        await stickers_collection.insert_one({
            "user_id": user_id,
            "file_unique_id": file_unique_id,
            "file_id": sticker.file_id,
            "emoji": emoji,
            "sticker_type": sticker_type,
            "pack_name": pack_name,
            "added_at": datetime.utcnow()
        })
        await message.reply(
            f"Sticker added to your {sticker_type} pack!\n"
            f"<a href='https://t.me/addstickers/{pack_name}'>Open pack</a>",
            parse_mode="HTML"
        )

async def list_sticker_packs(message: Message, db):
    user_id = message.from_user.id
    packs_collection = db["sticker_packs"]

    packs = await packs_collection.find({"user_id": user_id, "deleted": {"$ne": True}}).to_list(length=20)
    if not packs:
        await message.reply("You don't have any sticker packs yet. Send me stickers to create your pack!")
        return

    keyboard = [
        [InlineKeyboardButton(
            text=f"{(p.get('sticker_type') or 'static').capitalize()} Pack {p.get('index', '?')}",
            url=f"https://t.me/addstickers/{p['name']}"
        )]
        for p in packs
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.reply("Your sticker packs:", reply_markup=markup)
