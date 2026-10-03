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

ACCOUNT_TYPES = [
    "شخصي",
    "تجاري",
    "استثماري",
    "وزاري",
    "حكومي",
    "مخصص",
]


# =========================================================
# WEB SERVER - RENDER
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
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_database():

    conn = get_db()
    cur = conn.cursor()

    # =====================================================
    # SECTORS
    # =====================================================

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

    # =====================================================
    # BANK SETTINGS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_settings (
            guild_id INTEGER PRIMARY KEY,
            request_channel_id INTEGER,
            government_role_id INTEGER,
            ministerial_role_id INTEGER
        )
    """)

    # =====================================================
    # BANK ACCOUNTS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            account_name TEXT NOT NULL,
            account_age TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            account_type TEXT NOT NULL,
            extra_info TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    """)

    # =====================================================
    # BANK APPLICATIONS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            account_name TEXT NOT NULL,
            account_age TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            account_type TEXT NOT NULL,
            extra_info TEXT,
            channel_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by INTEGER,
            review_reason TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        )
    """)

    # =====================================================
    # TRANSACTIONS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            performed_by INTEGER NOT NULL,
            target_account_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    # =====================================================
    # LOAN PERMISSIONS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS loan_permissions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    # =====================================================
    # LOANS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            remaining INTEGER NOT NULL,
            reason TEXT NOT NULL,
            ticket_channel_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            approved_by INTEGER,
            created_at TEXT NOT NULL,
            approved_at TEXT
        )
    """)

    # =====================================================
    # VIOLATIONS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            details TEXT NOT NULL,
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # =====================================================
    # CASES
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'مفتوحة',
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # =====================================================
    # SERVICE SUSPENSIONS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS service_suspensions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            added_by INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            removed_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# GENERAL HELPERS
# =========================================================

def money(value):
    return f"{int(value):,}"


def is_admin(interaction: discord.Interaction):

    return (
        interaction.guild is not None
        and interaction.user.guild_permissions.administrator
    )


def get_setting(guild_id, name):

    conn = get_db()

    row = conn.execute("""
        SELECT value
        FROM rp_settings
        WHERE guild_id = ?
        AND setting_name = ?
    """, (guild_id, name)).fetchone()

    conn.close()

    return row["value"] if row else None


def set_setting(guild_id, name, value):

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS rp_settings (
            guild_id INTEGER NOT NULL,
            setting_name TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (guild_id, setting_name)
        )
    """)

    conn.execute("""
        INSERT INTO rp_settings
        (guild_id, setting_name, value)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, setting_name)
        DO UPDATE SET value = excluded.value
    """, (guild_id, name, value))

    conn.commit()
    conn.close()


def get_bank_settings(guild_id):

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM bank_settings
        WHERE guild_id = ?
    """, (guild_id,)).fetchone()

    conn.close()

    return row


def get_account(guild_id, account_id):

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM bank_accounts
        WHERE guild_id = ?
        AND id = ?
    """, (
        guild_id,
        account_id
    )).fetchone()

    conn.close()

    return row


def get_accounts(guild_id, owner_id):

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM bank_accounts
        WHERE guild_id = ?
        AND owner_id = ?
        ORDER BY id DESC
    """, (
        guild_id,
        owner_id
    )).fetchall()

    conn.close()

    return rows


def has_service_suspension(guild_id, user_id):

    conn = get_db()

    row = conn.execute("""
        SELECT id
        FROM service_suspensions
        WHERE guild_id = ?
        AND user_id = ?
        AND active = 1
        LIMIT 1
    """, (
        guild_id,
        user_id
    )).fetchone()

    conn.close()

    return row is not None


def log_transaction(
    guild_id,
    account_id,
    user_id,
    transaction_type,
    amount,
    reason,
    performed_by,
    target_account_id=None
):

    conn = get_db()

    conn.execute("""
        INSERT INTO transactions
        (
            guild_id,
            account_id,
            user_id,
            transaction_type,
            amount,
            reason,
            performed_by,
            target_account_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        guild_id,
        account_id,
        user_id,
        transaction_type,
        amount,
        reason,
        performed_by,
        target_account_id,
        now_iso()
    ))

    conn.commit()
    conn.close()


# =========================================================
# SECTOR SYSTEM
# =========================================================

def get_sector_role(guild_id, sector):

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

    return row["role_id"] if row else None


def set_sector_role(guild_id, sector, role_id):

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
        DO UPDATE SET role_id = excluded.role_id
    """, (
        guild_id,
        sector,
        role_id
    ))

    conn.commit()
    conn.close()


def has_sector_permission(interaction, sector):

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


def save_announcement(
    guild_id,
    sector,
    user_id,
    channel_id,
    message
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
        now_iso()
    ))

    conn.commit()
    conn.close()


class SectorSelect(discord.ui.Select):

    def __init__(self, mode):

        self.mode = mode

        options = [
            discord.SelectOption(
                label=sector,
                emoji=emoji,
                value=sector
            )
            for sector, emoji in SECTORS.items()
        ]

        super().__init__(
            placeholder="اختر القطاع أو الوزارة",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):

        sector = self.values[0]

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

        if self.mode == "setup":

            if not is_admin(interaction):

                await interaction.response.send_message(
                    "❌ هذا الأمر للإدارة فقط.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                f"⚙️ إعداد قطاع **{sector}**\n\n"
                "اختر رتبة القطاع:",
                view=RoleSelectView(sector),
                ephemeral=True
            )


class SectorView(discord.ui.View):

    def __init__(self, mode):

        super().__init__(timeout=180)
        self.add_item(SectorSelect(mode))


class SectorRoleSelect(discord.ui.RoleSelect):

    def __init__(self, sector):

        self.sector = sector

        super().__init__(
            placeholder="اختر رتبة القطاع"
        )

    async def callback(self, interaction):

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

        super().__init__(timeout=180)
        self.add_item(SectorRoleSelect(sector))


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
            max_length=4000
        )

        self.add_item(self.message_input)

    async def on_submit(self, interaction):

        await interaction.response.send_message(
            "📢 اختر الروم:",
            view=ChannelSelectView(
                self.sector,
                self.message_input.value
            ),
            ephemeral=True
        )


class AnnouncementChannelSelect(discord.ui.ChannelSelect):

    def __init__(self, sector, message):

        self.sector = sector
        self.message = message

        super().__init__(
            placeholder="اختر روم التعميم",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news
            ]
        )

    async def callback(self, interaction):

        channel = self.values[0]

        if not isinstance(channel, discord.TextChannel):

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
                "❌ ما عندك صلاحية.",
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

            role = interaction.guild.get_role(role_id)

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

        embed.set_footer(text="CTRP")

        try:

            await channel.send(
                content=role_mention or None,
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
                f"✅ تم إرسال التعميم في {channel.mention}.",
                ephemeral=True
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ البوت ما عنده صلاحية في الروم.",
                ephemeral=True
            )


class ChannelSelectView(discord.ui.View):

    def __init__(self, sector, message):

        super().__init__(timeout=180)

        self.add_item(
            AnnouncementChannelSelect(
                sector,
                message
            )
        )


# =========================================================
# SECTOR COMMANDS
# =========================================================

@bot.tree.command(
    name="تعميم",
    description="إرسال تعميم رسمي"
)
async def announcement_command(interaction):

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


@bot.tree.command(
    name="rp_اعداد",
    description="إعداد رتب القطاعات"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def rp_setup_command(interaction):

    await interaction.response.send_message(
        "⚙️ **إعداد قطاعات CTRP**\n\n"
        "اختر القطاع ثم الرتبة:",
        view=SectorView("setup"),
        ephemeral=True
    )


@bot.tree.command(
    name="rp_الحالة",
    description="عرض إعدادات القطاعات"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def rp_status_command(interaction):

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

            role = interaction.guild.get_role(role_id)

            value = (
                role.mention
                if role
                else f"`{role_id}`"
            )

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


@bot.tree.command(
    name="تعاميم_السجل",
    description="عرض سجل التعميمات"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def announcement_logs_command(interaction):

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
            "📭 لا يوجد تعاميم.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📋 سجل التعميمات",
        color=discord.Color.dark_blue()
    )

    for row in rows:

        message = row["message"]

        if len(message) > 200:
            message = message[:200] + "..."

        embed.add_field(
            name=f"{SECTORS.get(row['sector'], '📢')} {row['sector']}",
            value=(
                f"**المرسل:** <@{row['user_id']}>\n"
                f"**الروم:** <#{row['channel_id']}>\n"
                f"**التعميم:** {message}"
            ),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# BANK APPLICATION MODAL
# =========================================================

class BankApplicationModal(discord.ui.Modal):

    def __init__(self, owner, account_type):

        self.owner = owner
        self.account_type = account_type

        super().__init__(
            title="فتح حساب بنكي"
        )

        self.account_name = discord.ui.TextInput(
            label="اسم الحساب",
            placeholder="مثال: حساب شركة كريستال",
            required=True,
            max_length=100
        )

        self.account_age = discord.ui.TextInput(
            label="عمر الحساب",
            placeholder="مثال: سنة / سنتين",
            required=True,
            max_length=50
        )

        self.birth_date = discord.ui.TextInput(
            label="تاريخ الميلاد",
            placeholder="مثال: 2005/10/15",
            required=True,
            max_length=30
        )

        self.extra_info = discord.ui.TextInput(
            label="الأسئلة والمعلومات الإضافية",
            placeholder="اكتب الإجابات والمعلومات المطلوبة...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )

        self.add_item(self.account_name)
        self.add_item(self.account_age)
        self.add_item(self.birth_date)
        self.add_item(self.extra_info)

    async def on_submit(self, interaction):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                "❌ الأمر داخل السيرفر فقط.",
                ephemeral=True
            )
            return

        # ================================================
        # CHECK SPECIAL ACCOUNT TYPES
        # ================================================

        settings = get_bank_settings(guild.id)

        if self.account_type == "حكومي":

            role_id = (
                settings["government_role_id"]
                if settings
                else None
            )

            if not role_id or not any(
                role.id == role_id
                for role in self.owner.roles
            ):

                await interaction.response.send_message(
                    "❌ ما عند صاحب الحساب الرتبة المسموح لها بفتح الحساب الحكومي.",
                    ephemeral=True
                )
                return

        if self.account_type == "وزاري":

            role_id = (
                settings["ministerial_role_id"]
                if settings
                else None
            )

            if not role_id or not any(
                role.id == role_id
                for role in self.owner.roles
            ):

                await interaction.response.send_message(
                    "❌ ما عند صاحب الحساب الرتبة المسموح لها بفتح الحساب الوزاري.",
                    ephemeral=True
                )
                return

        # ================================================
        # REQUEST CHANNEL
        # ================================================

        request_channel_id = (
            settings["request_channel_id"]
            if settings
            else None
        )

        if not request_channel_id:

            await interaction.response.send_message(
                "❌ الإدارة لم تحدد روم طلبات فتح الحسابات.",
                ephemeral=True
            )
            return

        request_channel = guild.get_channel(
            request_channel_id
        )

        if not request_channel:

            await interaction.response.send_message(
                "❌ روم طلبات الحسابات غير موجود.",
                ephemeral=True
            )
            return

        # ================================================
        # SAVE APPLICATION
        # ================================================

        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO bank_applications
            (
                guild_id,
                owner_id,
                account_name,
                account_age,
                birth_date,
                account_type,
                extra_info,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            guild.id,
            self.owner.id,
            self.account_name.value,
            self.account_age.value,
            self.birth_date.value,
            self.account_type,
            self.extra_info.value,
            now_iso()
        ))

        application_id = cursor.lastrowid

        conn.commit()
        conn.close()

        # ================================================
        # EMBED
        # ================================================

        embed = discord.Embed(
            title="🏦 طلب فتح حساب بنكي",
            description=(
                f"يوجد طلب جديد لفتح حساب.\n\n"
                f"**صاحب الحساب:** {self.owner.mention}"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="🏦 نوع الحساب",
            value=self.account_type,
            inline=True
        )

        embed.add_field(
            name="📛 اسم الحساب",
            value=self.account_name.value,
            inline=True
        )

        embed.add_field(
            name="⏳ عمر الحساب",
            value=self.account_age.value,
            inline=True
        )

        embed.add_field(
            name="🎂 تاريخ الميلاد",
            value=self.birth_date.value,
            inline=True
        )

        embed.add_field(
            name="📝 الأسئلة والمعلومات",
            value=self.extra_info.value[:1024],
            inline=False
        )

        embed.add_field(
            name="🆔 رقم الطلب",
            value=f"`#{application_id}`",
            inline=True
        )

        embed.set_footer(
            text="CTRP Bank System"
        )

        try:

            message = await request_channel.send(
                embed=embed,
                view=BankApplicationView(
                    application_id
                )
            )

            conn = get_db()

            conn.execute("""
                UPDATE bank_applications
                SET channel_id = ?
                WHERE id = ?
            """, (
                message.channel.id,
                application_id
            ))

            conn.commit()
            conn.close()

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ البوت لا يستطيع إرسال الطلب في الروم المحدد.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "✅ تم إرسال طلب فتح الحساب للإدارة.\n"
            f"**صاحب الحساب:** {self.owner.mention}\n"
            f"**النوع:** {self.account_type}\n"
            f"**رقم الطلب:** `#{application_id}`",
            ephemeral=True
        )


# =========================================================
# BANK APPLICATION APPROVAL
# =========================================================

class BankRejectModal(discord.ui.Modal):

    def __init__(self, application_id):

        self.application_id = application_id

        super().__init__(
            title="رفض طلب الحساب"
        )

        self.reason = discord.ui.TextInput(
            label="سبب الرفض",
            placeholder="اكتب سبب رفض الطلب...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.add_item(self.reason)

    async def on_submit(self, interaction):

        if not is_admin(interaction):

            await interaction.response.send_message(
                "❌ هذا الزر للإدارة فقط.",
                ephemeral=True
            )
            return

        conn = get_db()

        row = conn.execute("""
            SELECT *
            FROM bank_applications
            WHERE id = ?
            AND guild_id = ?
        """, (
            self.application_id,
            interaction.guild.id
        )).fetchone()

        if not row:

            conn.close()

            await interaction.response.send_message(
                "❌ الطلب غير موجود.",
                ephemeral=True
            )
            return

        if row["status"] != "pending":

            conn.close()

            await interaction.response.send_message(
                "❌ هذا الطلب تمت معالجته مسبقًا.",
                ephemeral=True
            )
            return

        conn.execute("""
            UPDATE bank_applications
            SET
                status = 'rejected',
                reviewed_by = ?,
                review_reason = ?,
                reviewed_at = ?
            WHERE id = ?
        """, (
            interaction.user.id,
            self.reason.value,
            now_iso(),
            self.application_id
        ))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"❌ تم رفض طلب الحساب **#{self.application_id}**.\n"
            f"**السبب:** {self.reason.value}"
        )

        try:

            owner = interaction.guild.get_member(
                row["owner_id"]
            )

            if owner:

                await owner.send(
                    f"❌ تم رفض طلب فتح حسابك البنكي.\n\n"
                    f"**نوع الحساب:** {row['account_type']}\n"
                    f"**اسم الحساب:** {row['account_name']}\n"
                    f"**السبب:** {self.reason.value}"
                )

        except Exception:
            pass


class BankApplicationView(discord.ui.View):

    def __init__(self, application_id):

        super().__init__(
            timeout=None
        )

        self.application_id = application_id

    @discord.ui.button(
        label="قبول",
        style=discord.ButtonStyle.success,
        emoji="✅"
    )
    async def approve(
        self,
        interaction,
        button
    ):

        if not is_admin(interaction):

            await interaction.response.send_message(
                "❌ هذا الزر للإدارة فقط.",
                ephemeral=True
            )
            return

        conn = get_db()

        row = conn.execute("""
            SELECT *
            FROM bank_applications
            WHERE id = ?
            AND guild_id = ?
        """, (
            self.application_id,
            interaction.guild.id
        )).fetchone()

        if not row:

            conn.close()

            await interaction.response.send_message(
                "❌ الطلب غير موجود.",
                ephemeral=True
            )
            return

        if row["status"] != "pending":

            conn.close()

            await interaction.response.send_message(
                "❌ هذا الطلب تمت معالجته مسبقًا.",
                ephemeral=True
            )
            return

        # ================================================
        # CREATE ACCOUNT
        # ================================================

        cursor = conn.execute("""
            INSERT INTO bank_accounts
            (
                guild_id,
                owner_id,
                account_name,
                account_age,
                birth_date,
                account_type,
                extra_info,
                balance,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'active', ?)
        """, (
            row["guild_id"],
            row["owner_id"],
            row["account_name"],
            row["account_age"],
            row["birth_date"],
            row["account_type"],
            row["extra_info"],
            now_iso()
        ))

        account_id = cursor.lastrowid

        conn.execute("""
            UPDATE bank_applications
            SET
                status = 'approved',
                reviewed_by = ?,
                reviewed_at = ?
            WHERE id = ?
        """, (
            interaction.user.id,
            now_iso(),
            self.application_id
        ))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ **تم قبول طلب الحساب #{self.application_id}**\n\n"
            f"**صاحب الحساب:** <@{row['owner_id']}>\n"
            f"**نوع الحساب:** {row['account_type']}\n"
            f"**اسم الحساب:** {row['account_name']}\n"
            f"**رقم الحساب:** `{account_id}`"
        )

        try:

            owner = interaction.guild.get_member(
                row["owner_id"]
            )

            if owner:

                await owner.send(
                    f"✅ تم قبول طلب فتح حسابك البنكي.\n\n"
                    f"**نوع الحساب:** {row['account_type']}\n"
                    f"**اسم الحساب:** {row['account_name']}\n"
                    f"**رقم الحساب:** `{account_id}`\n"
                    f"**الرصيد:** 0"
                )

        except Exception:
            pass

    @discord.ui.button(
        label="رفض",
        style=discord.ButtonStyle.danger,
        emoji="❌"
    )
    async def reject(
        self,
        interaction,
        button
    ):

        if not is_admin(interaction):

            await interaction.response.send_message(
                "❌ هذا الزر للإدارة فقط.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            BankRejectModal(
                self.application_id
            )
        )


# =========================================================
# /فتح_حساب
# =========================================================

@bot.tree.command(
    name="فتح_حساب",
    description="تقديم طلب فتح حساب بنكي"
)
@app_commands.describe(
    صاحب_الحساب="صاحب الحساب",
    نوع_الحساب="نوع الحساب"
)
@app_commands.choices(
    نوع_الحساب=[
        app_commands.Choice(
            name="شخصي",
            value="شخصي"
        ),
        app_commands.Choice(
            name="تجاري",
            value="تجاري"
        ),
        app_commands.Choice(
            name="استثماري",
            value="استثماري"
        ),
        app_commands.Choice(
            name="وزاري",
            value="وزاري"
        ),
        app_commands.Choice(
            name="حكومي",
            value="حكومي"
        ),
        app_commands.Choice(
            name="مخصص",
            value="مخصص"
        ),
    ]
)
async def open_bank_account(
    interaction,
    صاحب_الحساب: discord.Member,
    نوع_الحساب: app_commands.Choice[str]
):

    if not interaction.guild:

        await interaction.response.send_message(
            "❌ الأمر داخل السيرفر فقط.",
            ephemeral=True
        )
        return

    # منع غير الإداري من فتح حساب لشخص آخر
    if (
        صاحب_الحساب.id != interaction.user.id
        and not is_admin(interaction)
    ):

        await interaction.response.send_message(
            "❌ تقدر تفتح حساب لنفسك فقط.",
            ephemeral=True
        )
        return

    await interaction.response.send_modal(
        BankApplicationModal(
            صاحب_الحساب,
            نوع_الحساب.value
        )
    )


# =========================================================
# BANK SETTINGS - REQUEST ROOM
# =========================================================

@bot.tree.command(
    name="البنك_تحديد_روم",
    description="تحديد روم طلبات فتح الحسابات"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    الروم="الروم الذي تصل إليه طلبات فتح الحساب"
)
async def bank_set_channel(
    interaction,
    الروم: discord.TextChannel
):

    conn = get_db()

    conn.execute("""
        INSERT INTO bank_settings
        (
            guild_id,
            request_channel_id
        )
        VALUES (?, ?)

        ON CONFLICT(guild_id)
        DO UPDATE SET
            request_channel_id = excluded.request_channel_id
    """, (
        interaction.guild.id,
        الروم.id
    ))

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ تم تحديد روم طلبات فتح الحسابات: {الروم.mention}",
        ephemeral=True
    )


# =========================================================
# BANK SETTINGS - GOVERNMENT ROLE
# =========================================================

@bot.tree.command(
    name="البنك_رتبة_حكومي",
    description="تحديد الرتبة التي يسمح لها بفتح الحساب الحكومي"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    الرتبة="الرتبة المسموح لها"
)
async def bank_set_government_role(
    interaction,
    الرتبة: discord.Role
):

    conn = get_db()

    conn.execute("""
        INSERT INTO bank_settings
        (
            guild_id,
            government_role_id
        )
        VALUES (?, ?)

        ON CONFLICT(guild_id)
        DO UPDATE SET
            government_role_id = excluded.government_role_id
    """, (
        interaction.guild.id,
        الرتبة.id
    ))

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ تم تحديد رتبة الحسابات الحكومية: {الرتبة.mention}",
        ephemeral=True
    )


# =========================================================
# BANK SETTINGS - MINISTERIAL ROLE
# =========================================================

@bot.tree.command(
    name="البنك_رتبة_وزاري",
    description="تحديد الرتبة التي يسمح لها بفتح الحساب الوزاري"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    الرتبة="الرتبة المسموح لها"
)
async def bank_set_ministerial_role(
    interaction,
    الرتبة: discord.Role
):

    conn = get_db()

    conn.execute("""
        INSERT INTO bank_settings
        (
            guild_id,
            ministerial_role_id
        )
        VALUES (?, ?)

        ON CONFLICT(guild_id)
        DO UPDATE SET
            ministerial_role_id = excluded.ministerial_role_id
    """, (
        interaction.guild.id,
        الرتبة.id
    ))

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ تم تحديد رتبة الحسابات الوزارية: {الرتبة.mention}",
        ephemeral=True
    )


# =========================================================
# BANK SETTINGS STATUS
# =========================================================

@bot.tree.command(
    name="البنك_الحالة",
    description="عرض إعدادات البنك"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def bank_status(interaction):

    settings = get_bank_settings(
        interaction.guild.id
    )

    if not settings:

        await interaction.response.send_message(
            "❌ لم يتم إعداد البنك.",
            ephemeral=True
        )
        return

    channel = (
        interaction.guild.get_channel(
            settings["request_channel_id"]
        )
        if settings["request_channel_id"]
        else None
    )

    gov_role = (
        interaction.guild.get_role(
            settings["government_role_id"]
        )
        if settings["government_role_id"]
        else None
    )

    minister_role = (
        interaction.guild.get_role(
            settings["ministerial_role_id"]
        )
        if settings["ministerial_role_id"]
        else None
    )

    embed = discord.Embed(
        title="🏦 إعدادات البنك",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="📨 روم الطلبات",
        value=channel.mention if channel else "❌ غير محدد",
        inline=False
    )

    embed.add_field(
        name="🏛️ رتبة الحكومي",
        value=gov_role.mention if gov_role else "❌ غير محددة",
        inline=False
    )

    embed.add_field(
        name="🏢 رتبة الوزاري",
        value=minister_role.mention if minister_role else "❌ غير محددة",
        inline=False
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /حساباتي
# =========================================================

@bot.tree.command(
    name="حساباتي",
    description="عرض جميع حساباتك البنكية"
)
async def my_accounts(interaction):

    rows = get_accounts(
        interaction.guild.id,
        interaction.user.id
    )

    if not rows:

        await interaction.response.send_message(
            "🏦 ما عندك أي حسابات بنكية.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🏦 حساباتك البنكية",
        color=discord.Color.blue()
    )

    for row in rows:

        embed.add_field(
            name=f"#{row['id']} ・ {row['account_name']}",
            value=(
                f"**النوع:** {row['account_type']}\n"
                f"**الرصيد:** {money(row['balance'])}\n"
                f"**الحالة:** {row['status']}"
            ),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /حساب
# =========================================================

@bot.tree.command(
    name="حساب",
    description="عرض تفاصيل حساب بنكي"
)
@app_commands.describe(
    رقم_الحساب="رقم الحساب"
)
async def account_details(
    interaction,
    رقم_الحساب: int
):

    account = get_account(
        interaction.guild.id,
        رقم_الحساب
    )

    if not account:

        await interaction.response.send_message(
            "❌ الحساب غير موجود.",
            ephemeral=True
        )
        return

    if (
        account["owner_id"] != interaction.user.id
        and not is_admin(interaction)
    ):

        await interaction.response.send_message(
            "❌ هذا الحساب ليس تابعًا لك.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🏦 تفاصيل الحساب",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="🆔 رقم الحساب",
        value=f"`{account['id']}",
        inline=True
    )

    embed.add_field(
        name="📛 اسم الحساب",
        value=account["account_name"],
        inline=True
    )

    embed.add_field(
        name="👤 صاحب الحساب",
        value=f"<@{account['owner_id']}>",
        inline=True
    )

    embed.add_field(
        name="🏦 النوع",
        value=account["account_type"],
        inline=True
    )

    embed.add_field(
        name="💰 الرصيد",
        value=money(account["balance"]),
        inline=True
    )

    embed.add_field(
        name="📌 الحالة",
        value=account["status"],
        inline=True
    )

    embed.add_field(
        name="⏳ عمر الحساب",
        value=account["account_age"],
        inline=True
    )

    embed.add_field(
        name="🎂 تاريخ الميلاد",
        value=account["birth_date"],
        inline=True
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /رصيدي
# =========================================================

@bot.tree.command(
    name="رصيدي",
    description="عرض أرصدة حساباتك"
)
async def balance_command(interaction):

    rows = get_accounts(
        interaction.guild.id,
        interaction.user.id
    )

    if not rows:

        await interaction.response.send_message(
            "❌ ما عندك حساب بنكي.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="💰 أرصدتك البنكية",
        color=discord.Color.green()
    )

    total = 0

    for row in rows:

        total += row["balance"]

        embed.add_field(
            name=f"#{row['id']} ・ {row['account_name']}",
            value=f"💰 **{money(row['balance'])}**",
            inline=True
        )

    embed.add_field(
        name="💵 إجمالي الأرصدة",
        value=f"**{money(total)}**",
        inline=False
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /إضافة_مبلغ
# =========================================================

@bot.tree.command(
    name="إضافة_مبلغ",
    description="إضافة مبلغ إلى حساب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    الحساب="رقم الحساب",
    المبلغ="المبلغ",
    السبب="سبب الإضافة"
)
async def add_money(
    interaction,
    الحساب: int,
    المبلغ: int,
    السبب: str
):

    if المبلغ <= 0:

        await interaction.response.send_message(
            "❌ المبلغ يجب أن يكون أكبر من صفر.",
            ephemeral=True
        )
        return

    account = get_account(
        interaction.guild.id,
        الحساب
    )

    if not account:

        await interaction.response.send_message(
            "❌ الحساب غير موجود.",
            ephemeral=True
        )
        return

    conn = get_db()

    conn.execute("""
        UPDATE bank_accounts
        SET balance = balance + ?
        WHERE guild_id = ?
        AND id = ?
    """, (
        المبلغ,
        interaction.guild.id,
        الحساب
    ))

    conn.commit()
    conn.close()

    log_transaction(
        interaction.guild.id,
        الحساب,
        account["owner_id"],
        "إضافة مبلغ",
        المبلغ,
        السبب,
        interaction.user.id
    )

    await interaction.response.send_message(
        f"✅ تم إضافة **{money(المبلغ)}** إلى الحساب `#{الحساب}`.\n"
        f"**السبب:** {السبب}\n"
        f"**بواسطة:** {interaction.user.mention}",
        ephemeral=True
    )


# =========================================================
# /خصم_مبلغ
# =========================================================

@bot.tree.command(
    name="خصم_مبلغ",
    description="خصم مبلغ من حساب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    الحساب="رقم الحساب",
    المبلغ="المبلغ",
    السبب="سبب الخصم"
)
async def remove_money(
    interaction,
    الحساب: int,
    المبلغ: int,
    السبب: str
):

    if المبلغ <= 0:

        await interaction.response.send_message(
            "❌ المبلغ يجب أن يكون أكبر من صفر.",
            ephemeral=True
        )
        return

    account = get_account(
        interaction.guild.id,
        الحساب
    )

    if not account:

        await interaction.response.send_message(
            "❌ الحساب غير موجود.",
            ephemeral=True
        )
        return

    if account["balance"] < المبلغ:

        await interaction.response.send_message(
            "❌ رصيد الحساب لا يكفي.",
            ephemeral=True
        )
        return

    conn = get_db()

    conn.execute("""
        UPDATE bank_accounts
        SET balance = balance - ?
        WHERE guild_id = ?
        AND id = ?
    """, (
        المبلغ,
        interaction.guild.id,
        الحساب
    ))

    conn.commit()
    conn.close()

    log_transaction(
        interaction.guild.id,
        الحساب,
        account["owner_id"],
        "خصم مبلغ",
        المبلغ,
        السبب,
        interaction.user.id
    )

    await interaction.response.send_message(
        f"✅ تم خصم **{money(المبلغ)}** من الحساب `#{الحساب}`.\n"
        f"**السبب:** {السبب}\n"
        f"**بواسطة:** {interaction.user.mention}",
        ephemeral=True
    )


# =========================================================
# /تحويل
# =========================================================

@bot.tree.command(
    name="تحويل",
    description="تحويل مبلغ من حسابك إلى حساب آخر"
)
@app_commands.describe(
    من_الحساب="رقم حسابك",
    إلى_الحساب="رقم الحساب المستلم",
    المبلغ="المبلغ"
)
async def transfer_money(
    interaction,
    من_الحساب: int,
    إلى_الحساب: int,
    المبلغ: int
):

    if المبلغ <= 0:

        await interaction.response.send_message(
            "❌ المبلغ يجب أن يكون أكبر من صفر.",
            ephemeral=True
        )
        return

    if من_الحساب == إلى_الحساب:

        await interaction.response.send_message(
            "❌ لا يمكنك التحويل إلى نفس الحساب.",
            ephemeral=True
        )
        return

    if has_service_suspension(
        interaction.guild.id,
        interaction.user.id
    ):

        await interaction.response.send_message(
            "❌ لا يمكنك إجراء تحويل أثناء إيقاف الخدمات.",
            ephemeral=True
        )
        return

    sender = get_account(
        interaction.guild.id,
        من_الحساب
    )

    receiver = get_account(
        interaction.guild.id,
        إلى_الحساب
    )

    if not sender:

        await interaction.response.send_message(
            "❌ حسابك غير موجود.",
            ephemeral=True
        )
        return

    if sender["owner_id"] != interaction.user.id:

        await interaction.response.send_message(
            "❌ الحساب المرسل ليس تابعًا لك.",
            ephemeral=True
        )
        return

    if not receiver:

        await interaction.response.send_message(
            "❌ الحساب المستلم غير موجود.",
            ephemeral=True
        )
        return

    if sender["balance"] < المبلغ:

        await interaction.response.send_message(
            "❌ رصيدك لا يكفي.",
            ephemeral=True
        )
        return

    conn = get_db()

    conn.execute("""
        UPDATE bank_accounts
        SET balance = balance - ?
        WHERE id = ?
        AND guild_id = ?
    """, (
        المبلغ,
        من_الحساب,
        interaction.guild.id
    ))

    conn.execute("""
        UPDATE bank_accounts
        SET balance = balance + ?
        WHERE id = ?
        AND guild_id = ?
    """, (
        المبلغ,
        إلى_الحساب,
        interaction.guild.id
    ))

    conn.commit()
    conn.close()

    log_transaction(
        interaction.guild.id,
        من_الحساب,
        interaction.user.id,
        "تحويل صادر",
        المبلغ,
        f"تحويل إلى الحساب #{إلى_الحساب}",
        interaction.user.id,
        إلى_الحساب
    )

    log_transaction(
        interaction.guild.id,
        إلى_الحساب,
        receiver["owner_id"],
        "تحويل وارد",
        المبلغ,
        f"تحويل من الحساب #{من_الحساب}",
        interaction.user.id,
        من_الحساب
    )

    await interaction.response.send_message(
        f"✅ تم التحويل بنجاح.\n\n"
        f"**من:** `#{من_الحساب}`\n"
        f"**إلى:** `#{إلى_الحساب}`\n"
        f"**المبلغ:** 💰 {money(المبلغ)}",
        ephemeral=True
    )


# =========================================================
# TRANSACTION LOG
# =========================================================

@bot.tree.command(
    name="سجل_مالي",
    description="عرض سجل العمليات المالية"
)
@app_commands.describe(
    اللاعب="اتركه فارغًا لعرض سجلك"
)
async def transaction_log(
    interaction,
    اللاعب: discord.Member = None
):

    target = اللاعب or interaction.user

    if (
        target.id != interaction.user.id
        and not is_admin(interaction)
    ):

        await interaction.response.send_message(
            "❌ لا يمكنك مشاهدة السجل المالي لشخص آخر.",
            ephemeral=True
        )
        return

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM transactions
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
        LIMIT 15
    """, (
        interaction.guild.id,
        target.id
    )).fetchall()

    conn.close()

    if not rows:

        await interaction.response.send_message(
            "📭 لا توجد عمليات مالية.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"📋 السجل المالي - {target.display_name}",
        color=discord.Color.blue()
    )

    for row in rows:

        sign = (
            "+"
            if row["transaction_type"] in
            ["إضافة مبلغ", "تحويل وارد", "قرض"]
            else "-"
        )

        embed.add_field(
            name=f"{row['transaction_type']} ・ {sign}{money(row['amount'])}",
            value=(
                f"**الحساب:** `#{row['account_id']}`\n"
                f"**السبب:** {row['reason']}\n"
                f"**بواسطة:** <@{row['performed_by']}>"
            ),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# LOAN PERMISSION
# =========================================================

@bot.tree.command(
    name="قرض_صلاحية",
    description="السماح أو منع شخص من طلب قرض"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    اللاعب="اللاعب",
    السماح="هل يسمح له؟"
)
@app_commands.choices(
    السماح=[
        app_commands.Choice(
            name="سماح",
            value="allow"
        ),
        app_commands.Choice(
            name="منع",
            value="deny"
        )
    ]
)
async def loan_permission(
    interaction,
    اللاعب: discord.Member,
    السماح: app_commands.Choice[str]
):

    allowed = 1 if السماح.value == "allow" else 0

    conn = get_db()

    conn.execute("""
        INSERT INTO loan_permissions
        (
            guild_id,
            user_id,
            allowed
        )
        VALUES (?, ?, ?)

        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET allowed = excluded.allowed
    """, (
        interaction.guild.id,
        اللاعب.id,
        allowed
    ))

    conn.commit()
    conn.close()

    text = "السماح" if allowed else "المنع"

    await interaction.response.send_message(
        f"✅ تم **{text}** لـ {اللاعب.mention} باستخدام نظام القروض.",
        ephemeral=True
    )


def loan_allowed(guild_id, user_id):

    conn = get_db()

    row = conn.execute("""
        SELECT allowed
        FROM loan_permissions
        WHERE guild_id = ?
        AND user_id = ?
    """, (
        guild_id,
        user_id
    )).fetchone()

    conn.close()

    return bool(row and row["allowed"])


# =========================================================
# LOAN REQUEST
# =========================================================

class LoanModal(discord.ui.Modal):

    def __init__(self, owner):

        self.owner = owner

        super().__init__(
            title="طلب قرض"
        )

        self.account_id = discord.ui.TextInput(
            label="رقم الحساب",
            placeholder="اكتب رقم الحساب",
            required=True,
            max_length=20
        )

        self.amount = discord.ui.TextInput(
            label="مبلغ القرض",
            placeholder="مثال: 50000",
            required=True,
            max_length=20
        )

        self.reason = discord.ui.TextInput(
            label="سبب القرض",
            placeholder="سبب طلب القرض",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.add_item(self.account_id)
        self.add_item(self.amount)
        self.add_item(self.reason)

    async def on_submit(self, interaction):

        try:
            account_id = int(self.account_id.value)
            amount = int(self.amount.value)
        except ValueError:

            await interaction.response.send_message(
                "❌ رقم الحساب والمبلغ يجب أن يكونا أرقامًا.",
                ephemeral=True
            )
            return

        if amount <= 0:

            await interaction.response.send_message(
                "❌ مبلغ القرض غير صحيح.",
                ephemeral=True
            )
            return

        account = get_account(
            interaction.guild.id,
            account_id
        )

        if not account:

            await interaction.response.send_message(
                "❌ الحساب غير موجود.",
                ephemeral=True
            )
            return

        if account["owner_id"] != self.owner.id:

            await interaction.response.send_message(
                "❌ الحساب ليس تابعًا لك.",
                ephemeral=True
            )
            return

        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO loans
            (
                guild_id,
                user_id,
                account_id,
                amount,
                remaining,
                reason,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            interaction.guild.id,
            self.owner.id,
            account_id,
            amount,
            amount,
            self.reason.value,
            now_iso()
        ))

        loan_id = cursor.lastrowid

        conn.commit()
        conn.close()

        # ================================================
        # CREATE TICKET
        # ================================================

        guild = interaction.guild

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            self.owner: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }

        channel = await guild.create_text_channel(
            name=f"قرض-{loan_id}",
            overwrites=overwrites,
            reason="طلب قرض"
        )

        conn = get_db()

        conn.execute("""
            UPDATE loans
            SET ticket_channel_id = ?
            WHERE id = ?
        """, (
            channel.id,
            loan_id
        ))

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="💳 طلب قرض جديد",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="👤 صاحب الطلب",
            value=self.owner.mention,
            inline=True
        )

        embed.add_field(
            name="🏦 الحساب",
            value=f"`#{account_id}`",
            inline=True
        )

        embed.add_field(
            name="💰 المبلغ",
            value=money(amount),
            inline=True
        )

        embed.add_field(
            name="📝 السبب",
            value=self.reason.value,
            inline=False
        )

        embed.add_field(
            name="🆔 رقم القرض",
            value=f"`#{loan_id}`",
            inline=True
        )

        await channel.send(
            content=self.owner.mention,
            embed=embed,
            view=LoanApprovalView(loan_id)
        )

        await interaction.response.send_message(
            f"✅ تم فتح طلب القرض في {channel.mention}.",
            ephemeral=True
        )


class LoanRejectModal(discord.ui.Modal):

    def __init__(self, loan_id):

        self.loan_id = loan_id

        super().__init__(
            title="رفض القرض"
        )

        self.reason = discord.ui.TextInput(
            label="سبب الرفض",
            placeholder="اكتب سبب رفض القرض...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.add_item(self.reason)

    async def on_submit(self, interaction):

        if not is_admin(interaction):

            await interaction.response.send_message(
                "❌ للإدارة فقط.",
                ephemeral=True
            )
            return

        conn = get_db()

        row = conn.execute("""
            SELECT *
            FROM loans
            WHERE id = ?
            AND guild_id = ?
        """, (
            self.loan_id,
            interaction.guild.id
        )).fetchone()

        if not row:

            conn.close()

            await interaction.response.send_message(
                "❌ القرض غير موجود.",
                ephemeral=True
            )
            return

        if row["status"] != "pending":

            conn.close()

            await interaction.response.send_message(
                "❌ تمت معالجة القرض مسبقًا.",
                ephemeral=True
            )
            return

        conn.execute("""
            UPDATE loans
            SET status = 'rejected',
                approved_by = ?,
                approved_at = ?
            WHERE id = ?
        """, (
            interaction.user.id,
            now_iso(),
            self.loan_id
        ))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"❌ تم رفض القرض `#{self.loan_id}`.\n"
            f"**السبب:** {self.reason.value}"
        )


class LoanApprovalView(discord.ui.View):

    def __init__(self, loan_id):

        super().__init__(
            timeout=None
        )

        self.loan_id = loan_id

    @discord.ui.button(
        label="قبول القرض",
        style=discord.ButtonStyle.success,
        emoji="✅"
    )
    async def approve(
        self,
        interaction,
        button
    ):

        if not is_admin(interaction):

            await interaction.response.send_message(
                "❌ للإدارة فقط.",
                ephemeral=True
            )
            return

        conn = get_db()

        row = conn.execute("""
            SELECT *
            FROM loans
            WHERE id = ?
            AND guild_id = ?
        """, (
            self.loan_id,
            interaction.guild.id
        )).fetchone()

        if not row:

            conn.close()

            await interaction.response.send_message(
                "❌ القرض غير موجود.",
                ephemeral=True
            )
            return

        if row["status"] != "pending":

            conn.close()

            await interaction.response.send_message(
                "❌ تمت معالجة القرض مسبقًا.",
                ephemeral=True
            )
            return

        # إيداع مبلغ القرض
        conn.execute("""
            UPDATE bank_accounts
            SET balance = balance + ?
            WHERE guild_id = ?
            AND id = ?
        """, (
            row["amount"],
            row["guild_id"],
            row["account_id"]
        ))

        conn.execute("""
            UPDATE loans
            SET
                status = 'approved',
                approved_by = ?,
                approved_at = ?
            WHERE id = ?
        """, (
            interaction.user.id,
            now_iso(),
            self.loan_id
        ))

        conn.commit()
        conn.close()

        log_transaction(
            interaction.guild.id,
            row["account_id"],
            row["user_id"],
            "قرض",
            row["amount"],
            f"اعتماد قرض #{self.loan_id}",
            interaction.user.id
        )

        await interaction.response.send_message(
            f"✅ تم قبول القرض `#{self.loan_id}`.\n"
            f"💰 تم إيداع **{money(row['amount'])}** في الحساب `#{row['account_id']}`."
        )

    @discord.ui.button(
        label="رفض القرض",
        style=discord.ButtonStyle.danger,
        emoji="❌"
    )
    async def reject(
        self,
        interaction,
        button
    ):

        if not is_admin(interaction):

            await interaction.response.send_message(
                "❌ للإدارة فقط.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            LoanRejectModal(
                self.loan_id
            )
        )


# =========================================================
# /قرض
# =========================================================

@bot.tree.command(
    name="قرض",
    description="تقديم طلب قرض"
)
async def loan_command(interaction):

    if not loan_allowed(
        interaction.guild.id,
        interaction.user.id
    ):

        await interaction.response.send_message(
            "❌ أنت غير مصرح لك باستخدام نظام القروض.",
            ephemeral=True
        )
        return

    await interaction.response.send_modal(
        LoanModal(interaction.user)
    )


# =========================================================
# /قروضي
# =========================================================

@bot.tree.command(
    name="قروضي",
    description="عرض قروضك"
)
async def my_loans(interaction):

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM loans
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
    """, (
        interaction.guild.id,
        interaction.user.id
    )).fetchall()

    conn.close()

    if not rows:

        await interaction.response.send_message(
            "📭 ما عندك قروض.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="💳 قروضك",
        color=discord.Color.gold()
    )

    for row in rows:

        embed.add_field(
            name=f"قرض #{row['id']}",
            value=(
                f"**المبلغ:** {money(row['amount'])}\n"
                f"**المتبقي:** {money(row['remaining'])}\n"
                f"**الحالة:** {row['status']}\n"
                f"**السبب:** {row['reason']}"
            ),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# ADMIN ADD LOAN
# =========================================================

@bot.tree.command(
    name="إضافة_قرض",
    description="إضافة قرض مباشر للاعب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    الحساب="رقم الحساب",
    المبلغ="مبلغ القرض",
    السبب="سبب القرض"
)
async def admin_add_loan(
    interaction,
    الحساب: int,
    المبلغ: int,
    السبب: str
):

    if المبلغ <= 0:

        await interaction.response.send_message(
            "❌ المبلغ غير صحيح.",
            ephemeral=True
        )
        return

    account = get_account(
        interaction.guild.id,
        الحساب
    )

    if not account:

        await interaction.response.send_message(
            "❌ الحساب غير موجود.",
            ephemeral=True
        )
        return

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO loans
        (
            guild_id,
            user_id,
            account_id,
            amount,
            remaining,
            reason,
            status,
            approved_by,
            created_at,
            approved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'approved', ?, ?, ?)
    """, (
        interaction.guild.id,
        account["owner_id"],
        الحساب,
        المبلغ,
        المبلغ,
        السبب,
        interaction.user.id,
        now_iso(),
        now_iso()
    ))

    loan_id = cursor.lastrowid

    conn.execute("""
        UPDATE bank_accounts
        SET balance = balance + ?
        WHERE guild_id = ?
        AND id = ?
    """, (
        المبلغ,
        interaction.guild.id,
        الحساب
    ))

    conn.commit()
    conn.close()

    log_transaction(
        interaction.guild.id,
        الحساب,
        account["owner_id"],
        "قرض",
        المبلغ,
        f"إضافة قرض #{loan_id}: {السبب}",
        interaction.user.id
    )

    await interaction.response.send_message(
        f"✅ تمت إضافة القرض `#{loan_id}`.\n"
        f"💰 المبلغ: **{money(المبلغ)}**\n"
        f"🏦 الحساب: `#{الحساب}`\n"
        f"📝 السبب: {السبب}",
        ephemeral=True
    )


# =========================================================
# VIOLATIONS
# =========================================================

@bot.tree.command(
    name="إضافة_مخالفة",
    description="إضافة مخالفة للاعب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    اللاعب="اللاعب",
    العنوان="عنوان المخالفة",
    التفاصيل="تفاصيل المخالفة"
)
async def add_violation(
    interaction,
    اللاعب: discord.Member,
    العنوان: str,
    التفاصيل: str
):

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO violations
        (
            guild_id,
            user_id,
            title,
            details,
            added_by,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        interaction.guild.id,
        اللاعب.id,
        العنوان,
        التفاصيل,
        interaction.user.id,
        now_iso()
    ))

    violation_id = cursor.lastrowid

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ تمت إضافة المخالفة `#{violation_id}` إلى {اللاعب.mention}.",
        ephemeral=True
    )


@bot.tree.command(
    name="مخالفاتي",
    description="عرض مخالفاتك"
)
async def my_violations(interaction):

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM violations
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
    """, (
        interaction.guild.id,
        interaction.user.id
    )).fetchall()

    conn.close()

    if not rows:

        await interaction.response.send_message(
            "✅ ما عندك مخالفات.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="⚠️ مخالفاتك",
        color=discord.Color.orange()
    )

    for row in rows:

        embed.add_field(
            name=f"#{row['id']} ・ {row['title']}",
            value=row["details"],
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# CASES
# =========================================================

@bot.tree.command(
    name="إضافة_قضية",
    description="إضافة قضية للاعب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    اللاعب="اللاعب",
    العنوان="عنوان القضية",
    التفاصيل="تفاصيل القضية"
)
async def add_case(
    interaction,
    اللاعب: discord.Member,
    العنوان: str,
    التفاصيل: str
):

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO cases
        (
            guild_id,
            user_id,
            title,
            details,
            status,
            added_by,
            created_at
        )
        VALUES (?, ?, ?, ?, 'مفتوحة', ?, ?)
    """, (
        interaction.guild.id,
        اللاعب.id,
        العنوان,
        التفاصيل,
        interaction.user.id,
        now_iso()
    ))

    case_id = cursor.lastrowid

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ تمت إضافة القضية `#{case_id}` إلى {اللاعب.mention}.",
        ephemeral=True
    )


@bot.tree.command(
    name="قضاياي",
    description="عرض قضاياك"
)
async def my_cases(interaction):

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM cases
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
    """, (
        interaction.guild.id,
        interaction.user.id
    )).fetchall()

    conn.close()

    if not rows:

        await interaction.response.send_message(
            "📭 ما عندك قضايا.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="⚖️ قضاياك",
        color=discord.Color.dark_blue()
    )

    for row in rows:

        embed.add_field(
            name=f"القضية #{row['id']} ・ {row['title']}",
            value=(
                f"**الحالة:** {row['status']}\n"
                f"**التفاصيل:** {row['details']}"
            ),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


@bot.tree.command(
    name="تحديث_قضية",
    description="تغيير حالة قضية"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    رقم_القضية="رقم القضية",
    الحالة="الحالة الجديدة"
)
@app_commands.choices(
    الحالة=[
        app_commands.Choice(
            name="مفتوحة",
            value="مفتوحة"
        ),
        app_commands.Choice(
            name="مغلقة",
            value="مغلقة"
        ),
        app_commands.Choice(
            name="مؤجلة",
            value="مؤجلة"
        ),
    ]
)
async def update_case(
    interaction,
    رقم_القضية: int,
    الحالة: app_commands.Choice[str]
):

    conn = get_db()

    row = conn.execute("""
        SELECT id
        FROM cases
        WHERE id = ?
        AND guild_id = ?
    """, (
        رقم_القضية,
        interaction.guild.id
    )).fetchone()

    if not row:

        conn.close()

        await interaction.response.send_message(
            "❌ القضية غير موجودة.",
            ephemeral=True
        )
        return

    conn.execute("""
        UPDATE cases
        SET status = ?
        WHERE id = ?
        AND guild_id = ?
    """, (
        الحالة.value,
        رقم_القضية,
        interaction.guild.id
    ))

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ تم تحديث القضية `#{رقم_القضية}` إلى **{الحالة.value}**.",
        ephemeral=True
    )


# =========================================================
# SERVICE SUSPENSION
# =========================================================

@bot.tree.command(
    name="إيقاف_خدمات",
    description="إيقاف خدمات لاعب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    اللاعب="اللاعب",
    السبب="سبب إيقاف الخدمات"
)
async def suspend_services(
    interaction,
    اللاعب: discord.Member,
    السبب: str
):

    conn = get_db()

    conn.execute("""
        UPDATE service_suspensions
        SET active = 0
        WHERE guild_id = ?
        AND user_id = ?
        AND active = 1
    """, (
        interaction.guild.id,
        اللاعب.id
    ))

    conn.execute("""
        INSERT INTO service_suspensions
        (
            guild_id,
            user_id,
            reason,
            added_by,
            active,
            created_at
        )
        VALUES (?, ?, ?, ?, 1, ?)
    """, (
        interaction.guild.id,
        اللاعب.id,
        السبب,
        interaction.user.id,
        now_iso()
    ))

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"🛑 تم إيقاف خدمات {اللاعب.mention}.\n"
        f"**السبب:** {السبب}",
        ephemeral=True
    )


@bot.tree.command(
    name="رفع_إيقاف_خدمات",
    description="رفع إيقاف الخدمات عن لاعب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    اللاعب="اللاعب"
)
async def remove_suspension(
    interaction,
    اللاعب: discord.Member
):

    conn = get_db()

    cursor = conn.execute("""
        UPDATE service_suspensions
        SET
            active = 0,
            removed_at = ?
        WHERE guild_id = ?
        AND user_id = ?
        AND active = 1
    """, (
        now_iso(),
        interaction.guild.id,
        اللاعب.id
    ))

    changed = cursor.rowcount

    conn.commit()
    conn.close()

    if changed == 0:

        await interaction.response.send_message(
            "❌ اللاعب ليس عليه إيقاف خدمات.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"✅ تم رفع إيقاف الخدمات عن {اللاعب.mention}.",
        ephemeral=True
    )


# =========================================================
# FULL PLAYER FILE
# =========================================================

async def build_player_file(
    guild_id,
    user_id
):

    user = bot.get_user(user_id)

    accounts = get_accounts(
        guild_id,
        user_id
    )

    conn = get_db()

    violations = conn.execute("""
        SELECT *
        FROM violations
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
    """, (
        guild_id,
        user_id
    )).fetchall()

    cases = conn.execute("""
        SELECT *
        FROM cases
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
    """, (
        guild_id,
        user_id
    )).fetchall()

    loans = conn.execute("""
        SELECT *
        FROM loans
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY id DESC
    """, (
        guild_id,
        user_id
    )).fetchall()

    suspension = conn.execute("""
        SELECT *
        FROM service_suspensions
        WHERE guild_id = ?
        AND user_id = ?
        AND active = 1
        ORDER BY id DESC
        LIMIT 1
    """, (
        guild_id,
        user_id
    )).fetchone()

    conn.close()

    embed = discord.Embed(
        title="📁 الملف الشخصي الكامل",
        color=discord.Color.dark_blue()
    )

    embed.add_field(
        name="👤 اللاعب",
        value=f"<@{user_id}>",
        inline=True
    )

    embed.add_field(
        name="🆔 Discord ID",
        value=f"`{user_id}`",
        inline=True
    )

    # =====================================================
    # ACCOUNTS
    # =====================================================

    if accounts:

        account_text = ""

        for account in accounts[:10]:

            account_text += (
                f"`#{account['id']}` "
                f"**{account['account_name']}**\n"
                f"النوع: {account['account_type']} "
                f"・ الرصيد: {money(account['balance'])}\n\n"
            )

        embed.add_field(
            name="🏦 الحسابات البنكية",
            value=account_text[:1024],
            inline=False
        )

    else:

        embed.add_field(
            name="🏦 الحسابات البنكية",
            value="لا يوجد حسابات.",
            inline=False
        )

    # =====================================================
    # LOANS
    # =====================================================

    if loans:

        loan_text = ""

        for loan in loans[:10]:

            loan_text += (
                f"`#{loan['id']}` "
                f"{loan['status']} "
                f"・ المبلغ: {money(loan['amount'])} "
                f"・ المتبقي: {money(loan['remaining'])}\n"
            )

        embed.add_field(
            name="💳 القروض",
            value=loan_text[:1024],
            inline=False
        )

    else:

        embed.add_field(
            name="💳 القروض",
            value="لا يوجد قروض.",
            inline=False
        )

    # =====================================================
    # CASES
    # =====================================================

    if cases:

        case_text = ""

        for case in cases[:10]:

            case_text += (
                f"`#{case['id']}` "
                f"**{case['title']}** "
                f"・ {case['status']}\n"
            )

        embed.add_field(
            name="⚖️ القضايا",
            value=case_text[:1024],
            inline=False
        )

    else:

        embed.add_field(
            name="⚖️ القضايا",
            value="لا يوجد قضايا.",
            inline=False
        )

    # =====================================================
    # VIOLATIONS
    # =====================================================

    if violations:

        violation_text = ""

        for violation in violations[:10]:

            violation_text += (
                f"`#{violation['id']}` "
                f"**{violation['title']}**\n"
            )

        embed.add_field(
            name="⚠️ المخالفات",
            value=violation_text[:1024],
            inline=False
        )

    else:

        embed.add_field(
            name="⚠️ المخالفات",
            value="لا يوجد مخالفات.",
            inline=False
        )

    # =====================================================
    # SERVICE SUSPENSION
    # =====================================================

    if suspension:

        embed.add_field(
            name="🛑 إيقاف الخدمات",
            value=(
                "الحالة: **موقوف**\n"
                f"السبب: {suspension['reason']}"
            ),
            inline=False
        )

    else:

        embed.add_field(
            name="🛑 إيقاف الخدمات",
            value="✅ غير موقوف",
            inline=False
        )

    return embed


# =========================================================
# /ملفي
# =========================================================

@bot.tree.command(
    name="ملفي",
    description="عرض ملفك الكامل"
)
async def my_file(interaction):

    embed = await build_player_file(
        interaction.guild.id,
        interaction.user.id
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /ملف_لاعب
# =========================================================

@bot.tree.command(
    name="ملف_لاعب",
    description="عرض الملف الكامل للاعب"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    اللاعب="اللاعب"
)
async def player_file(
    interaction,
    اللاعب: discord.Member
):

    embed = await build_player_file(
        interaction.guild.id,
        اللاعب.id
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# UNIFIED ADMIN PLAYER MANAGEMENT
# =========================================================

@bot.tree.command(
    name="إدارة_ملف",
    description="إدارة ملف لاعب وإضافة بيانات"
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    اللاعب="اللاعب",
    النوع="نوع الإجراء",
    العنوان="العنوان أو السبب",
    التفاصيل="التفاصيل",
    المبلغ="المبلغ عند الحاجة"
)
@app_commands.choices(
    النوع=[
        app_commands.Choice(
            name="إضافة مخالفة",
            value="violation"
        ),
        app_commands.Choice(
            name="إضافة قضية",
            value="case"
        ),
        app_commands.Choice(
            name="إيقاف خدمات",
            value="suspend"
        ),
        app_commands.Choice(
            name="رفع إيقاف خدمات",
            value="unsuspend"
        ),
        app_commands.Choice(
            name="إضافة قرض",
            value="loan"
        ),
    ]
)
async def manage_player_file(
    interaction,
    اللاعب: discord.Member,
    النوع: app_commands.Choice[str],
    العنوان: str,
    التفاصيل: str,
    المبلغ: int = 0
):

    action = النوع.value

    # =====================================================
    # VIOLATION
    # =====================================================

    if action == "violation":

        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO violations
            (
                guild_id,
                user_id,
                title,
                details,
                added_by,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            interaction.guild.id,
            اللاعب.id,
            العنوان,
            التفاصيل,
            interaction.user.id,
            now_iso()
        ))

        violation_id = cursor.lastrowid

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ تمت إضافة المخالفة `#{violation_id}` إلى {اللاعب.mention}.",
            ephemeral=True
        )
        return

    # =====================================================
    # CASE
    # =====================================================

    if action == "case":

        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO cases
            (
                guild_id,
                user_id,
                title,
                details,
                status,
                added_by,
                created_at
            )
            VALUES (?, ?, ?, ?, 'مفتوحة', ?, ?)
        """, (
            interaction.guild.id,
            اللاعب.id,
            العنوان,
            التفاصيل,
            interaction.user.id,
            now_iso()
        ))

        case_id = cursor.lastrowid

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ تمت إضافة القضية `#{case_id}` إلى {اللاعب.mention}.",
            ephemeral=True
        )
        return

    # =====================================================
    # SUSPEND
    # =====================================================

    if action == "suspend":

        conn = get_db()

        conn.execute("""
            UPDATE service_suspensions
            SET active = 0
            WHERE guild_id = ?
            AND user_id = ?
            AND active = 1
        """, (
            interaction.guild.id,
            اللاعب.id
        ))

        conn.execute("""
            INSERT INTO service_suspensions
            (
                guild_id,
                user_id,
                reason,
                added_by,
                active,
                created_at
            )
            VALUES (?, ?, ?, ?, 1, ?)
        """, (
            interaction.guild.id,
            اللاعب.id,
            التفاصيل,
            interaction.user.id,
            now_iso()
        ))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"🛑 تم إيقاف خدمات {اللاعب.mention}.",
            ephemeral=True
        )
        return

    # =====================================================
    # UNSUSPEND
    # =====================================================

    if action == "unsuspend":

        conn = get_db()

        cursor = conn.execute("""
            UPDATE service_suspensions
            SET active = 0,
                removed_at = ?
            WHERE guild_id = ?
            AND user_id = ?
            AND active = 1
        """, (
            now_iso(),
            interaction.guild.id,
            اللاعب.id
        ))

        conn.commit()
        conn.close()

        if cursor.rowcount:

            await interaction.response.send_message(
                f"✅ تم رفع إيقاف الخدمات عن {اللاعب.mention}.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "❌ لا يوجد إيقاف خدمات فعال.",
                ephemeral=True
            )

        return

    # =====================================================
    # LOAN
    # =====================================================

    if action == "loan":

        if المبلغ <= 0:

            await interaction.response.send_message(
                "❌ يجب تحديد مبلغ للقرض.",
                ephemeral=True
            )
            return

        accounts = get_accounts(
            interaction.guild.id,
            اللاعب.id
        )

        if not accounts:

            await interaction.response.send_message(
                "❌ اللاعب لا يملك حسابًا بنكيًا.",
                ephemeral=True
            )
            return

        account = accounts[0]

        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO loans
            (
                guild_id,
                user_id,
                account_id,
                amount,
                remaining,
                reason,
                status,
                approved_by,
                created_at,
                approved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'approved', ?, ?, ?)
        """, (
            interaction.guild.id,
            اللاعب.id,
            account["id"],
            المبلغ,
            المبلغ,
            التفاصيل,
            interaction.user.id,
            now_iso(),
            now_iso()
        ))

        loan_id = cursor.lastrowid

        conn.execute("""
            UPDATE bank_accounts
            SET balance = balance + ?
            WHERE guild_id = ?
            AND id = ?
        """, (
            المبلغ,
            interaction.guild.id,
            account["id"]
        ))

        conn.commit()
        conn.close()

        log_transaction(
            interaction.guild.id,
            account["id"],
            اللاعب.id,
            "قرض",
            المبلغ,
            f"إضافة قرض #{loan_id}: {التفاصيل}",
            interaction.user.id
        )

        await interaction.response.send_message(
            f"✅ تمت إضافة القرض `#{loan_id}` إلى {اللاعب.mention}.\n"
            f"💰 المبلغ: **{money(المبلغ)}**",
            ephemeral=True
        )


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"✅ CTRP RP Bot logged in as {bot.user}"
    )

    try:

        # تسجيل أزرار الطلبات القديمة بعد إعادة التشغيل
        conn = get_db()

        applications = conn.execute("""
            SELECT id
            FROM bank_applications
            WHERE status = 'pending'
        """).fetchall()

        loans = conn.execute("""
            SELECT id
            FROM loans
            WHERE status = 'pending'
        """).fetchall()

        conn.close()

        for row in applications:

            try:
                bot.add_view(
                    BankApplicationView(row["id"])
                )
            except Exception:
                pass

        for row in loans:

            try:
                bot.add_view(
                    LoanApprovalView(row["id"])
                )
            except Exception:
                pass

        synced = await bot.tree.sync()

        print(
            f"✅ Synced {len(synced)} slash commands"
        )

        print(
            f"🏦 Pending bank applications: {len(applications)}"
        )

        print(
            f"💳 Pending loans: {len(loans)}"
        )

    except Exception as e:

        print(
            "❌ Ready Error:",
            e
        )


# =========================================================
# ERROR HANDLER
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):

        message = "❌ ما عندك صلاحية لاستخدام هذا الأمر."

    elif isinstance(
        error,
        app_commands.CommandOnCooldown
    ):

        message = "⏳ حاول مرة ثانية لاحقًا."

    else:

        print(
            "Command Error:",
            repr(error)
        )

        message = "❌ حدث خطأ أثناء تنفيذ الأمر."

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
# START
# =========================================================

if __name__ == "__main__":

    init_database()

    if not TOKEN:

        raise RuntimeError(
            "DISCORD_TOKEN غير موجود في Environment Variables"
        )

    web_thread = Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    bot.run(TOKEN)
