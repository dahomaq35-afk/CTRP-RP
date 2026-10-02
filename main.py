import os
import sqlite3
from datetime import datetime, timezone
from threading import Thread

from flask import Flask

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# SETTINGS
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

DB_FILE = "rp_bot.db"


SECTORS = {
    "وزارة العدل": "⚖️",
    "وزارة الداخلية": "🛡️",
    "IAA": "🕵️",
    "EMS": "🚑",
    "FBI": "🕶️",
    "وزارة الدفاع": "🪖",
    "LSPD": "👮",
    "SWAT": "🚔",
}


# =========================================================
# FAKE WEB SERVER FOR RENDER
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "CTRP RP Bot is Online!"


@app.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================================================
# BOT
# =========================================================

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(DB_FILE)

    conn.row_factory = sqlite3.Row

    return conn


def init_database():

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_settings (
            guild_id INTEGER NOT NULL,
            sector TEXT NOT NULL,
            role_id INTEGER,
            PRIMARY KEY (guild_id, sector)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS announcement_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            sector TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()

    conn.close()


# =========================================================
# SECTOR SETTINGS
# =========================================================

def get_sector_role(
    guild_id: int,
    sector: str
):

    conn = get_db()

    row = conn.execute("""
        SELECT role_id
        FROM sector_settings
        WHERE guild_id = ?
        AND sector = ?
    """, (
        guild_id,
        sector
    )).fetchone()

    conn.close()

    if row:
        return row["role_id"]

    return None


def set_sector_role(
    guild_id: int,
    sector: str,
    role_id: int
):

    conn = get_db()

    conn.execute("""
        INSERT INTO sector_settings
        (
            guild_id,
            sector,
            role_id
        )
        VALUES (?, ?, ?)

        ON CONFLICT(guild_id, sector)
        DO UPDATE SET
            role_id = excluded.role_id
    """, (
        guild_id,
        sector,
        role_id
    ))

    conn.commit()

    conn.close()


# =========================================================
# PERMISSION
# =========================================================

def has_sector_permission(
    interaction: discord.Interaction,
    sector: str
):

    if not interaction.guild:
        return False

    if interaction.user.guild_permissions.administrator:
        return True

    role_id = get_sector_role(
        interaction.guild.id,
        sector
    )

    if not role_id:
        return False

    return any(
        role.id == role_id
        for role in interaction.user.roles
    )


# =========================================================
# SAVE ANNOUNCEMENT
# =========================================================

def save_announcement(
    guild_id: int,
    sector: str,
    user_id: int,
    channel_id: int,
    message: str
):

    conn = get_db()

    conn.execute("""
        INSERT INTO announcement_logs
        (
            guild_id,
            sector,
            user_id,
            channel_id,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        guild_id,
        sector,
        user_id,
        channel_id,
        message,
        datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()

    conn.close()


# =========================================================
# SECTOR SELECT
# =========================================================

class SectorSelect(discord.ui.Select):

    def __init__(self, mode):

        self.mode = mode

        options = []

        for sector, emoji in SECTORS.items():

            options.append(
                discord.SelectOption(
                    label=sector,
                    emoji=emoji,
                    value=sector
                )
            )

        super().__init__(
            placeholder="اختر القطاع أو الوزارة",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        sector = self.values[0]

        # =================================================
        # ANNOUNCEMENT
        # =================================================

        if self.mode == "announcement":

            if not has_sector_permission(
                interaction,
                sector
            ):

                await interaction.response.send_message(
                    "❌ ما عندك صلاحية لإرسال تعميم لهذا القطاع.",
                    ephemeral=True
                )

                return

            await interaction.response.send_modal(
                AnnouncementModal(sector)
            )

            return

        # =================================================
        # SETUP
        # =================================================

        if self.mode == "setup":

            if not interaction.user.guild_permissions.administrator:

                await interaction.response.send_message(
                    "❌ هذا الأمر للإدارة فقط.",
                    ephemeral=True
                )

                return

            await interaction.response.send_message(
                f"⚙️ إعداد قطاع **{sector}**\n\n"
                "اختر رتبة القطاع من القائمة:",
                view=RoleSelectView(sector),
                ephemeral=True
            )


# =========================================================
# SECTOR VIEW
# =========================================================

class SectorView(discord.ui.View):

    def __init__(self, mode):

        super().__init__(
            timeout=180
        )

        self.add_item(
            SectorSelect(mode)
        )


# =========================================================
# ROLE SELECT
# =========================================================

class SectorRoleSelect(discord.ui.RoleSelect):

    def __init__(self, sector):

        self.sector = sector

        super().__init__(
            placeholder="اختر رتبة القطاع",
            min_values=1,
            max_values=1
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        role = self.values[0]

        set_sector_role(
            interaction.guild.id,
            self.sector,
            role.id
        )

        await interaction.response.send_message(
            f"✅ تم ربط **{self.sector}** بالرتبة {role.mention}.",
            ephemeral=True
        )


class RoleSelectView(discord.ui.View):

    def __init__(self, sector):

        super().__init__(
            timeout=180
        )

        self.add_item(
            SectorRoleSelect(sector)
        )


# =========================================================
# ANNOUNCEMENT MODAL
# =========================================================

class AnnouncementModal(discord.ui.Modal):

    def __init__(self, sector):

        self.sector = sector

        super().__init__(
            title=f"تعميم {sector}"
        )

        self.message_input = discord.ui.TextInput(
            label="نص التعميم",
            placeholder="اكتب التعميم هنا...",
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=1,
            max_length=4000
        )

        self.add_item(
            self.message_input
        )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.send_message(
            "📢 اختر الروم الذي تريد إرسال التعميم فيه:",
            view=ChannelSelectView(
                self.sector,
                self.message_input.value
            ),
            ephemeral=True
        )


# =========================================================
# CHANNEL SELECT
# =========================================================

class AnnouncementChannelSelect(
    discord.ui.ChannelSelect
):

    def __init__(
        self,
        sector,
        message
    ):

        self.sector = sector
        self.message = message

        super().__init__(
            placeholder="اختر روم التعميم",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news
            ],
            min_values=1,
            max_values=1
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        channel = self.values[0]

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ الروم غير صالح.",
                ephemeral=True
            )

            return

        if not has_sector_permission(
            interaction,
            self.sector
        ):

            await interaction.response.send_message(
                "❌ ما عندك صلاحية لهذا القطاع.",
                ephemeral=True
            )

            return

        emoji = SECTORS[self.sector]

        role_id = get_sector_role(
            interaction.guild.id,
            self.sector
        )

        role_mention = ""

        if role_id:

            role = interaction.guild.get_role(
                role_id
            )

            if role:
                role_mention = role.mention

        embed = discord.Embed(
            title=f"{emoji} تعميم رسمي",
            description=self.message,
            color=discord.Color.dark_blue(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="القطاع",
            value=f"{emoji} {self.sector}",
            inline=True
        )

        embed.add_field(
            name="بواسطة",
            value=interaction.user.mention,
            inline=True
        )

        embed.set_footer(
            text="CTRP"
        )

        try:

            await channel.send(
                content=(
                    role_mention
                    if role_mention
                    else None
                ),
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    roles=True
                )
            )

            save_announcement(
                interaction.guild.id,
                self.sector,
                interaction.user.id,
                channel.id,
                self.message
            )

            await interaction.response.send_message(
                f"✅ تم إرسال التعميم بنجاح في {channel.mention}.",
                ephemeral=True
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ البوت ما عنده صلاحية إرسال الرسائل أو الـ Embed في هذا الروم.",
                ephemeral=True
            )

        except Exception as e:

            print(
                "Announcement Error:",
                e
            )

            await interaction.response.send_message(
                "❌ حدث خطأ أثناء إرسال التعميم.",
                ephemeral=True
            )


class ChannelSelectView(discord.ui.View):

    def __init__(
        self,
        sector,
        message
    ):

        super().__init__(
            timeout=180
        )

        self.add_item(
            AnnouncementChannelSelect(
                sector,
                message
            )
        )


# =========================================================
# /تعميم
# =========================================================

@bot.tree.command(
    name="تعميم",
    description="إرسال تعميم رسمي"
)
async def announcement_command(
    interaction: discord.Interaction
):

    if not interaction.guild:

        await interaction.response.send_message(
            "❌ الأمر داخل السيرفر فقط.",
            ephemeral=True
        )

        return

    await interaction.response.send_message(
        "📢 **نظام التعميمات الرسمية CTRP**\n\n"
        "اختر القطاع أو الوزارة:",
        view=SectorView("announcement"),
        ephemeral=True
    )


# =========================================================
# /rp_اعداد
# =========================================================

@bot.tree.command(
    name="rp_اعداد",
    description="إعداد رتبة القطاعات"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def rp_setup_command(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        "⚙️ **إعداد قطاعات CTRP**\n\n"
        "اختر القطاع ثم اختر الرتبة الخاصة به:",
        view=SectorView("setup"),
        ephemeral=True
    )


# =========================================================
# /تعاميم_السجل
# =========================================================

@bot.tree.command(
    name="تعاميم_السجل",
    description="عرض سجل آخر التعميمات"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def announcement_logs_command(
    interaction: discord.Interaction
):

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM announcement_logs
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 10
    """, (
        interaction.guild.id,
    )).fetchall()

    conn.close()

    if not rows:

        await interaction.response.send_message(
            "📭 لا يوجد تعاميم مسجلة.",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title="📋 سجل التعميمات",
        color=discord.Color.dark_blue()
    )

    for row in rows:

        channel = interaction.guild.get_channel(
            row["channel_id"]
        )

        user_text = f"<@{row['user_id']}>"

        channel_text = (
            channel.mention
            if channel
            else f"<#{row['channel_id']}>"
        )

        message = row["message"]

        if len(message) > 200:
            message = message[:200] + "..."

        embed.add_field(
            name=(
                f"{SECTORS.get(row['sector'], '📢')} "
                f"{row['sector']}"
            ),
            value=(
                f"**المرسل:** {user_text}\n"
                f"**الروم:** {channel_text}\n"
                f"**التعميم:** {message}"
            ),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /rp_الحالة
# =========================================================

@bot.tree.command(
    name="rp_الحالة",
    description="عرض حالة إعداد قطاعات CTRP"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def rp_status_command(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="⚙️ حالة قطاعات CTRP",
        color=discord.Color.dark_blue()
    )

    for sector, emoji in SECTORS.items():

        role_id = get_sector_role(
            interaction.guild.id,
            sector
        )

        if role_id:

            role = interaction.guild.get_role(
                role_id
            )

            if role:
                value = role.mention
            else:
                value = f"`{role_id}`"

        else:

            value = "❌ غير محدد"

        embed.add_field(
            name=f"{emoji} {sector}",
            value=value,
            inline=True
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# ERROR HANDLER
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):

        message = (
            "❌ ما عندك صلاحية لاستخدام هذا الأمر."
        )

    else:

        print(
            "Command Error:",
            error
        )

        message = (
            "❌ حدث خطأ أثناء تنفيذ الأمر."
        )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                message,
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                message,
                ephemeral=True
            )

    except Exception:
        pass


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"✅ CTRP RP Bot logged in as {bot.user}"
    )

    try:

        synced = await bot.tree.sync()

        print(
            f"✅ Synced {len(synced)} slash commands"
        )

    except Exception as e:

        print(
            "❌ Sync Error:",
            e
        )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    init_database()

    if not TOKEN:

        raise RuntimeError(
            "DISCORD_TOKEN غير موجود في Environment Variables"
        )

    # تشغيل السيرفر الوهمي لـ Render
    web_thread = Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    # تشغيل البوت
    bot.run(TOKEN)
