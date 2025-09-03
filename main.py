# -*- coding: utf-8 -*-
import os
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import datetime as dt
import random
import string

# 🔑 환경변수에서 토큰 불러오기
TOKEN = os.getenv("DISCORD_TOKEN")

DB_PATH = "licenses.db"
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# ========================
# DB 초기화
# ========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS license_codes (
        code TEXT PRIMARY KEY,
        type TEXT,
        created_at TEXT,
        used_by INTEGER,
        used_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        user_id INTEGER PRIMARY KEY,
        code TEXT,
        type TEXT,
        activated_at TEXT,
        expires_at TEXT
    )
    """)
    conn.commit()
    conn.close()


# ========================
# 라이선스 코드 생성 함수
# ========================
def generate_license(lic_type: str):
    random_part = "-".join(
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        for _ in range(3)
    )
    return f"Wind-Banner-{random_part}-{lic_type}"


# ========================
# 라이선스 등록 모달
# ========================
class LicenseModal(discord.ui.Modal, title="라이선스 등록"):
    code = discord.ui.TextInput(label="라이선스 코드", placeholder="Wind-Banner-XXXXX-XXXXX-XXXXX-7D")

    async def on_submit(self, interaction: discord.Interaction):
        code = str(self.code).strip()
        user_id = interaction.user.id
        now = dt.datetime.utcnow()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("SELECT type, used_by FROM license_codes WHERE code=?", (code,))
        row = cur.fetchone()

        if not row:
            return await interaction.response.send_message("❌ 존재하지 않는 코드입니다.", ephemeral=True)

        lic_type, used_by = row
        if used_by is not None:
            return await interaction.response.send_message("❌ 이미 사용된 코드입니다.", ephemeral=True)

        # 코드 기간 설정
        if lic_type == "7D":
            expires = now + dt.timedelta(days=7)
            lic_label = "7일"
        elif lic_type == "30D":
            expires = now + dt.timedelta(days=30)
            lic_label = "30일"
        elif lic_type == "PERM":
            expires = None
            lic_label = "영구"
        else:
            expires = now + dt.timedelta(days=1)
            lic_label = "1회용"

        # 유저 라이선스 등록
        cur.execute(
            "REPLACE INTO licenses (user_id, code, type, activated_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, code, lic_label, now.isoformat(), expires.isoformat() if expires else None)
        )

        # 코드 사용 처리
        cur.execute(
            "UPDATE license_codes SET used_by=?, used_at=? WHERE code=?",
            (user_id, now.isoformat(), code)
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"✅ {lic_label} 라이선스 등록 완료!", ephemeral=True)


# ========================
# 버튼 뷰
# ========================
class LicenseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="등록하기", style=discord.ButtonStyle.green, custom_id="register")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LicenseModal())

    @discord.ui.button(label="내정보", style=discord.ButtonStyle.blurple, custom_id="myinfo")
    async def myinfo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT type, activated_at, expires_at FROM licenses WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            embed = discord.Embed(title="❌ 라이선스 없음", description="등록된 라이선스가 없습니다.", color=discord.Color.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lic_type, activated_at, expires_at = row
        activated_at = dt.datetime.fromisoformat(activated_at).strftime("%Y-%m-%d %H:%M")

        if lic_type == "영구":
            embed = discord.Embed(title="📜 라이선스 정보", color=discord.Color.gold())
            embed.add_field(name="종류", value="영구", inline=False)
            embed.add_field(name="등록일", value=activated_at, inline=False)
        else:
            exp = dt.datetime.fromisoformat(expires_at)
            now = dt.datetime.utcnow()
            remaining = exp - now

            if remaining.total_seconds() <= 0:
                embed = discord.Embed(title="⛔ 라이선스 만료", color=discord.Color.red())
                embed.add_field(name="등록일", value=activated_at, inline=False)
                embed.add_field(name="만료일", value=exp.strftime("%Y-%m-%d %H:%M"), inline=False)
            else:
                days = remaining.days
                hours = remaining.seconds // 3600
                embed = discord.Embed(title="✅ 라이선스 활성화됨", color=discord.Color.green())
                embed.add_field(name="종류", value=lic_type, inline=False)
                embed.add_field(name="등록일", value=activated_at, inline=False)
                embed.add_field(name="만료일", value=exp.strftime("%Y-%m-%d %H:%M"), inline=False)
                embed.add_field(name="남은 기간", value=f"{days}일 {hours}시간", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ========================
# 슬래시 명령어
# ========================
@bot.tree.command(name="배너등록", description="배너 등록 버튼을 보여줍니다")
async def 배너등록(interaction: discord.Interaction):
    view = LicenseView()
    await interaction.response.send_message("배너 등록하기", view=view)


@bot.tree.command(name="코드생성", description="(관리자 전용) 라이선스 코드를 생성합니다 (7D / 30D / PERM)")
async def 코드생성(interaction: discord.Interaction, 종류: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)

    code = generate_license(종류.upper())
    now = dt.datetime.utcnow()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO license_codes (code, type, created_at, used_by, used_at) VALUES (?, ?, ?, NULL, NULL)",
        (code, 종류.upper(), now.isoformat())
    )
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ 생성된 코드: `{code}`", ephemeral=True)


# ========================
# 실행
# ========================
@bot.event
async def on_ready():
    init_db()
    try:
        synced = await bot.tree.sync()
        print(f"✅ 슬래시 명령어 동기화 완료: {len(synced)}개")
    except Exception as e:
        print(f"슬래시 명령어 동기화 실패: {e}")
    print(f"✅ 로그인 성공: {bot.user}")


bot.run(TOKEN)
