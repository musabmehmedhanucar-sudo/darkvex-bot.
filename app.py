import os
from flask import Flask
import threading
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
from datetime import datetime, timedelta, timezone
import requests
import xml.etree.ElementTree as ET
import re

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "006 Master Bot 7/24 Aktif ve Calisiyor!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# --- MASTER DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 0. AUTO ROLE ON JOIN
@bot.event
async def on_member_join(member: discord.Member):
    role = discord.utils.get(member.guild.roles, name="Member")
    if role:
        try:
            await member.add_roles(role)
        except Exception as e:
            print(f"Oto rol verme hatası: {e}")

# 1. TICKET SYSTEM
class CloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Talebi Kapat", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("🔒 Destek talebi kapatılıyor...", ephemeral=True)
        await interaction.channel.delete()

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Destek Talebi Aç", style=discord.ButtonStyle.success, emoji="🛡️", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="006 TICKETS")
        if not category:
            category = await guild.create_category("006 TICKETS")

        existing_channel = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing_channel:
            await interaction.response.send_message(f"⚠️ Zaten açık bir talebin bulunuyor: {existing_channel.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        for role in guild.roles:
            if role.name in ["👤Üye", "Subscriber", "Member"]:
                overwrites[role] = discord.PermissionOverwrite(view_channel=False)

        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="⬜ 006 | Destek Talebi",
            description=f"Merhaba {interaction.user.mention}!\n\nYetkili ekibimiz en kısa sürede seninle ilgilenecektir.",
            color=0x000000
        )
        embed.set_footer(text="006 Security & Support", icon_url=bot.user.display_avatar.url if bot.user else None)
        
        await channel.send(embed=embed, view=CloseView())
        await interaction.response.send_message(f"✅ Destek talebin başarıyla oluşturuldu: {channel.mention}", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    embed = discord.Embed(
        title="⚪ 006 SUPPORT CENTER",
        description="Yardıma mı ihtiyacın var?\nBir sorun, öneri veya şikayetin için aşağıdan destek talebi oluşturabilirsin.\n\n*Yetkililer en kısa sürede seninle iletişime geçecektir.*",
        color=0x000000
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url if bot.user else None)
    embed.set_footer(text="006 Security - 2026", icon_url=bot.user.display_avatar.url if bot.user else None)
    await ctx.send(embed=embed, view=TicketView())

honeypot_data = {
    "mutes_count": 0,
    "embed_message_id": None,
    "embed_channel_id": None,
    "webhook_id": None
}

@bot.command(name="honey", aliases=["honeypot"])
@commands.has_permissions(administrator=True)
async def honeypot_setup(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
        
    webhooks = await ctx.channel.webhooks()
    webhook = discord.utils.get(webhooks, name="006 Honeypot")
    if not webhook:
        try:
            webhook = await ctx.channel.create_webhook(name="006 Honeypot")
        except Exception as e:
            print(f"Webhook oluşturma hatası: {e}")

    embed = discord.Embed(
        title="MESAJ YAZARSAN MUTE YERSİN | IF YOU SEND MESSAGE YOU WILL GET MUTE",
        description="Bu kanal r4t yiyenleri yakalamak için, mesaj yazarsan mute yersin. | This channel trap for r4t users, if you send message you will get mute.",
        color=0xD4AF37
    )
    embed.add_field(name="🍯 Mute", value=f"`{honeypot_data['mutes_count']}`", inline=False)
    embed.set_footer(text="006 Security & Honeypot System", icon_url=bot.user.display_avatar.url if bot.user else None)
    
    if webhook:
        msg = await webhook.send(
            embed=embed,
            username="Honeypot",
            avatar_url="https://images.emojiterra.com/google/android-11/512px/1f36f.png",
            wait=True
        )
        honeypot_data["embed_message_id"] = msg.id
        honeypot_data["embed_channel_id"] = ctx.channel.id
        honeypot_data["webhook_id"] = webhook.id
    else:
        msg = await ctx.send(embed=embed)
        honeypot_data["embed_message_id"] = msg.id
        honeypot_data["embed_channel_id"] = ctx.channel.id

# 2. PUNISHMENT LOGGING (CEZALAR)
async def send_punishment_embed(guild: discord.Guild, title: str, description: str, color: int):
    channel = None
    for c in guild.text_channels:
        if "ceza-kanalı" in c.name or "⛔ceza-kanalı" in c.name:
            channel = c
            break
    if not channel:
        channel = await guild.create_text_channel("⛔ceza-kanalı")
    
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now())
    embed.set_footer(text="006 Security & Justice System", icon_url=bot.user.display_avatar.url if bot.user else None)
    await channel.send(embed=embed)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    moderator = "Bilinmiyor"
    reason = "Belirtilmedi"
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
        if entry.target.id == user.id:
            moderator = entry.user.mention
            reason = entry.reason if entry.reason else "Belirtilmedi"
            break
    desc = f"⚠️ **Ceza Alan Üye:** {user.mention} (`{user.name}`)\n🛡️ **İşlemi Yapan:** {moderator}\n⚖️ **Tür:** Sunucudan Kalıcı Ban\n📝 **Gerekçe:** `{reason}`"
    await send_punishment_embed(guild, "🏳️ 006 | YENİ BAN CEZASI", desc, 0x000000)

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.timed_out_until != after.timed_out_until and after.timed_out_until is not None:
        moderator = "Bilinmiyor"
        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
            if entry.target.id == after.id:
                moderator = entry.user.mention
                break
        delta = after.timed_out_until - datetime.now(after.timed_out_until.tzinfo)
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        duration_str = f"{hours} saat {minutes} dakika" if hours > 0 else f"{minutes} dakika"
        desc = f"🔇 **Ceza Alan Üye:** {after.mention}\n🛡️ **İşlemi Yapan:** {moderator}\n⚖️ **Tür:** Susturma (Timeout)\n⏳ **Süre:** `{duration_str}`"
        await send_punishment_embed(guild=after.guild, title="🔇 006 | SUSTURMA CEZASI", description=desc, color=0xD4AF37)

# 3. SUGGESTION SYSTEM (ÖNERİ)
@bot.command(name="oneri")
async def oneri(ctx, *, content: str = None):
    if not content:
        await ctx.send("⚠️ Lütfen bir öneri belirtin!", delete_after=5)
        return
    try:
        await ctx.message.delete()
    except:
        pass

    target_channel = ctx.channel
    suggestion = content
    if ctx.message.channel_mentions:
        target_channel = ctx.message.channel_mentions[0]
        suggestion = content.replace(target_channel.mention, "").strip()

    embed = discord.Embed(
        title="⬜ 006 | YENİ TOPLULUK ÖNERİSİ",
        description=f"```{suggestion}```",
        color=0x000000,
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Öneren Üye", value=ctx.author.mention, inline=True)
    embed.add_field(name="📊 Oylama Durumu", value="⏳ `Değerlendiriliyor...`", inline=True)
    embed.set_author(name=f"{ctx.author.name} tarafından önerildi", icon_url=ctx.author.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url if bot.user else None)
    embed.set_footer(text=f"006 Community • {ctx.guild.name}", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)

    msg = await target_channel.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.command(name="oneribitir")
@commands.has_permissions(administrator=True)
async def oneribitir(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    target_channel = ctx.channel
    if ctx.message.channel_mentions:
        target_channel = ctx.message.channel_mentions[0]

    last_msg = None
    async for message in target_channel.history(limit=50):
        if message.author.id == bot.user.id and len(message.embeds) > 0:
            if "YENİ TOPLULUK ÖNERİSİ" in message.embeds[0].title:
                last_msg = message
                break

    if not last_msg:
        await ctx.send(f"⚠️ Aktif öneri bulunamadı!", delete_after=5)
        return

    upvotes, downvotes = 0, 0
    last_msg = await target_channel.fetch_message(last_msg.id)
    for reaction in last_msg.reactions:
        if str(reaction.emoji) == "👍":
            upvotes = reaction.count - 1
        elif str(reaction.emoji) == "👎":
            downvotes = reaction.count - 1

    decision = "✅ KABUL EDİLDİ" if upvotes > downvotes else ("❌ REDDEDİLDİ" if downvotes > upvotes else "🤝 BERABERE")
    decision_color = 0xD4AF37 if upvotes > downvotes else (0xD4AF37 if downvotes > upvotes else 0xD4AF37)

    orig_embed = last_msg.embeds[0]
    final_embed = discord.Embed(title=f"🗳️ 006 | ÖNERİ SONUÇLANDI", description=orig_embed.description, color=decision_color, timestamp=datetime.now())
    final_embed.set_author(name=orig_embed.author.name, icon_url=orig_embed.author.icon_url)
    final_embed.set_thumbnail(url=orig_embed.thumbnail.url)
    final_embed.add_field(name="👤 Öneren Üye", value=orig_embed.fields[0].value, inline=True)
    final_embed.add_field(name="📢 Karar", value=f"**{decision}**", inline=True)
    final_embed.add_field(name="👍 Onay", value=f"`{upvotes}`", inline=True)
    final_embed.add_field(name="👎 Red", value=f"`{downvotes}`", inline=True)
    final_embed.add_field(name="⚖️ Sonuç", value=f"Topluluk Önerisinde **{upvotes} onay** ve **{downvotes} red** alınmıştır. Öneri **{decision}** olarak işaretlendi.\n\n*Yetkililer yakında ilgilenecektir.*", inline=False)
    final_embed.set_footer(text=orig_embed.footer.text, icon_url=orig_embed.footer.icon_url)

    await last_msg.edit(embed=final_embed)
    await last_msg.clear_reactions()

# 5. COUNTING GAME SYSTEM (SAYI SAYMACA)
counting_data = {
    "current_number": 0,
    "last_user_id": None
}

@bot.command(name="basla")
@commands.has_permissions(administrator=True)
async def basla(ctx):
    global counting_data
    counting_data["current_number"] = 0
    counting_data["last_user_id"] = None
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await ctx.send("🧮 **Sayı Sayma Başladı! Son sayı: 0**")

@bot.event
async def on_message(message: discord.Message):
    global counting_data
    if message.author.bot:
        await bot.process_commands(message)
        return

    # Honeypot Check (Bedava Hile Kanalı Tuzağı)
    channel_name = message.channel.name.lower()
    print(f"[DEBUG] Mesaj algılandı. Kanal: {channel_name}, Yazar: {message.author}")
    if "bedava" in channel_name or "hile" in channel_name or "free" in channel_name or "hack" in channel_name:
        try:
            await message.delete()
        except Exception as e:
            print(f"Honeypot mesaj silme hatası: {e}")

        try:
            await message.author.timeout(timedelta(days=1), reason="Honeypot kanalına mesaj yazma girişimi (Bedava Hile Tuzağı)")
        except Exception as e:
            print(f"Honeypot timeout hatası: {e}")

        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        for c in message.guild.text_channels:
            try:
                await c.purge(limit=100, check=lambda m: m.author.id == message.author.id and m.created_at >= two_hours_ago)
            except Exception as e:
                print(f"Kanal temizleme hatası ({c.name}): {e}")

        honeypot_data["mutes_count"] += 1
        if honeypot_data["embed_message_id"] and honeypot_data["embed_channel_id"] == message.channel.id:
            try:
                ch = message.guild.get_channel(honeypot_data["embed_channel_id"])
                if ch:
                    if honeypot_data.get("webhook_id"):
                        try:
                            webhook = await ch.fetch_webhook(honeypot_data["webhook_id"])
                            embed = discord.Embed(
                                title="MESAJ YAZARSAN MUTE YERSİN | IF YOU SEND MESSAGE YOU WILL GET MUTE",
                                description="Bu kanal r4t yiyenleri yakalamak için, mesaj yazarsan mute yersin. | This channel trap for r4t users, if you send message you will get mute.",
                                color=0xD4AF37
                            )
                            embed.add_field(name="🍯 Mute", value=f"`{honeypot_data['mutes_count']}`", inline=False)
                            embed.set_footer(text="006 Security & Honeypot System", icon_url=bot.user.display_avatar.url if bot.user else None)
                            await webhook.edit_message(honeypot_data["embed_message_id"], embed=embed)
                        except:
                            msg_to_edit = await ch.fetch_message(honeypot_data["embed_message_id"])
                            embed = msg_to_edit.embeds[0]
                            embed.clear_fields()
                            embed.add_field(name="🍯 Mute", value=f"`{honeypot_data['mutes_count']}`", inline=False)
                            await msg_to_edit.edit(embed=embed)
                    else:
                        msg_to_edit = await ch.fetch_message(honeypot_data["embed_message_id"])
                        embed = msg_to_edit.embeds[0]
                        embed.clear_fields()
                        embed.add_field(name="🍯 Mute", value=f"`{honeypot_data['mutes_count']}`", inline=False)
                        await msg_to_edit.edit(embed=embed)
            except Exception as e:
                print(f"Honeypot embed güncelleme hatası: {e}")
        return

    if "sayı-saymaca" in message.channel.name.lower() or "saymaca" in message.channel.name.lower():
        content = message.content.strip()
        
        if content.startswith("!"):
            await bot.process_commands(message)
            return

        try:
            number = int(content)
        except ValueError:
            try:
                await message.delete()
            except:
                pass
            return

        expected_number = counting_data["current_number"] + 1

        if number == expected_number:
            counting_data["current_number"] = number
            counting_data["last_user_id"] = message.author.id
            try:
                kirmizi_tik = discord.utils.get(message.guild.emojis, name="kirmizitik")
                if kirmizi_tik:
                    await message.add_reaction(kirmizi_tik)
                else:
                    await message.add_reaction("✅")
            except:
                pass
        else:
            try:
                await message.delete()
            except:
                pass
            
            warn_msg = await message.channel.send(f"{message.author.mention} **Yanlış Yaptın, Tekrar Bak!** (Beklenen: `{expected_number}`)")
            import asyncio
            await asyncio.sleep(4)
            try:
                await warn_msg.delete()
            except:
                pass
            return

    await bot.process_commands(message)

# 4. YOUTUBE NOTIFIER SYSTEM (@006_mnfs) - Every 30 seconds
last_video_id = None

@tasks.loop(seconds=30)
async def check_youtube():
    global last_video_id
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get("https://www.youtube.com/@006_mnfs", headers=headers, timeout=10)
        if resp.status_code == 200:
            match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]+)"', resp.text)
            if match:
                channel_id = match.group(1)
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                rss_resp = requests.get(rss_url, timeout=10)
                if rss_resp.status_code == 200:
                    root = ET.fromstring(rss_resp.content)
                    ns = {'atom': 'http://www.w3.org/2005/Atom'}
                    entries = root.findall('atom:entry', ns)
                    if entries:
                        latest = entries[0]
                        vid_id = latest.find('atom:id', ns).text
                        vid_title = latest.find('atom:title', ns).text
                        vid_link = latest.find('atom:link', ns).attrib['href']
                        
                        if last_video_id is None:
                            last_video_id = vid_id
                        elif last_video_id != vid_id:
                            last_video_id = vid_id
                            for guild in bot.guilds:
                                channel = discord.utils.get(guild.text_channels, name="video-duyuru")
                                if not channel:
                                    channel = discord.utils.get(guild.text_channels, name="📷video-duyuru")
                                if channel:
                                    embed = discord.Embed(
                                        title="📢 YENİ VİDEO YAYINDA!",
                                        description=f"**{vid_title}**\n\n[Videoyu İzlemek İçin Tıkla]({vid_link})",
                                        color=0x000000,
                                        timestamp=datetime.now()
                                    )
                                    embed.set_thumbnail(url=bot.user.display_avatar.url if bot.user else None)
                                    embed.set_footer(text="006 YouTube RSS", icon_url=guild.icon.url if guild.icon else None)
                                    await channel.send(content="@everyone 🚀 **YENİ VİDEO ŞUAN KANALIMIZDA YAYINDA!** ||@here||", embed=embed)
    except Exception as int_e:
        print(f"YouTube kontrol hatası: {int_e}")

@check_youtube.before_loop
async def before_check_youtube():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    print(f"006 Master Bot aktif ve hazir: {bot.user.name}")
    if not check_youtube.is_running():
        check_youtube.start()

# --- MAIN RUNNER ---
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    TOKEN = os.environ.get("DISCORD Developer Portal" if False else "DISCORD_TOKEN")
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN bulunamadi!")
    bot.run(TOKEN)
