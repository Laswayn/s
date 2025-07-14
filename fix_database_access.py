#!/usr/bin/env python3
"""
Script to fix database access issues for recap and export features
"""

import os
import sqlite3
from pathlib import Path

def fix_database_access():
    """Fix database access permissions and path issues"""
    
    print("🔧 FIXING DATABASE ACCESS ISSUES")
    print("=" * 50)
    
    # Get current directory
    current_dir = Path.cwd()
    print(f"📁 Current directory: {current_dir}")
    
    # Define possible database locations
    db_locations = [
        current_dir / "instance" / "data_sensus.db",
        current_dir / "data_sensus.db",
        Path("/tmp") / "data_sensus.db"
    ]
    
    # Check existing database files
    existing_db = None
    for db_path in db_locations:
        if db_path.exists():
            print(f"✅ Found database at: {db_path}")
            existing_db = db_path
            break
    
    if not existing_db:
        print("❌ No existing database found. Creating new one...")
        # Create instance directory
        instance_dir = current_dir / "instance"
        instance_dir.mkdir(exist_ok=True, mode=0o755)
        existing_db = instance_dir / "data_sensus.db"
    
    # Ensure proper permissions
    try:
        # Set directory permissions
        instance_dir = existing_db.parent
        instance_dir.chmod(0o755)
        print(f"✅ Set directory permissions: {instance_dir}")
        
        # If database exists, set file permissions
        if existing_db.exists():
            existing_db.chmod(0o644)
            print(f"✅ Set file permissions: {existing_db}")
        
        # Test database connection
        test_connection(existing_db)
        
    except Exception as e:
        print(f"❌ Error setting permissions: {e}")
        return False
    
    return str(existing_db)

def test_connection(db_path):
    """Test database connection and create tables if needed"""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"📊 Database tables found: {[table[0] for table in tables]}")
        
        # Create tables if they don't exist
        if not tables:
            print("🔨 Creating database tables...")
            create_tables(cursor)
            conn.commit()
        
        # Test data access
        cursor.execute("SELECT COUNT(*) FROM keluarga;")
        family_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM individu;")
        individual_count = cursor.fetchone()[0]
        
        print(f"📈 Data found - Families: {family_count}, Individuals: {individual_count}")
        
        conn.close()
        print("✅ Database connection test successful!")
        return True
        
    except Exception as e:
        print(f"❌ Database connection test failed: {e}")
        return False

def create_tables(cursor):
    """Create database tables if they don't exist"""
    
    # Create user table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash VARCHAR(120) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create keluarga table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keluarga (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keluarga_id VARCHAR(50) UNIQUE NOT NULL,
            rt VARCHAR(10) NOT NULL,
            rw VARCHAR(10) NOT NULL,
            dusun VARCHAR(50) NOT NULL,
            nama_kepala VARCHAR(100) NOT NULL,
            alamat TEXT NOT NULL,
            jumlah_anggota INTEGER NOT NULL,
            jumlah_anggota_15plus INTEGER NOT NULL,
            nama_pencacah VARCHAR(100),
            hp_pencacah VARCHAR(20),
            tanggal_pencacah VARCHAR(50),
            nama_pemberi_jawaban VARCHAR(100),
            hp_pemberi_jawaban VARCHAR(20),
            tanggal_pemberi_jawaban VARCHAR(50),
            catatan TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create individu table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS individu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keluarga_id INTEGER NOT NULL,
            anggota_ke INTEGER NOT NULL,
            nama_anggota VARCHAR(100) NOT NULL,
            umur INTEGER NOT NULL,
            hubungan_kepala VARCHAR(50) NOT NULL,
            jenis_kelamin VARCHAR(20) NOT NULL,
            status_perkawinan VARCHAR(30) NOT NULL,
            pendidikan_terakhir VARCHAR(100) NOT NULL,
            kegiatan_sehari VARCHAR(100) NOT NULL,
            memiliki_pekerjaan VARCHAR(10) NOT NULL,
            status_pekerjaan_diinginkan VARCHAR(100),
            bidang_usaha_diminati VARCHAR(100),
            bidang_pekerjaan VARCHAR(200),
            memiliki_lebih_satu_pekerjaan VARCHAR(10),
            status_pekerjaan_utama VARCHAR(100),
            pemasaran_usaha_utama VARCHAR(50),
            penjualan_marketplace_utama VARCHAR(10),
            bidang_pekerjaan_sampingan1 VARCHAR(200),
            status_pekerjaan_sampingan1 VARCHAR(100),
            pemasaran_usaha_sampingan1 VARCHAR(50),
            penjualan_marketplace_sampingan1 VARCHAR(10),
            bidang_pekerjaan_sampingan2 VARCHAR(200),
            status_pekerjaan_sampingan2 VARCHAR(100),
            pemasaran_usaha_sampingan2 VARCHAR(50),
            penjualan_marketplace_sampingan2 VARCHAR(10),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (keluarga_id) REFERENCES keluarga (id)
        )
    ''')
    
    # Insert default users
    from werkzeug.security import generate_password_hash
    
    admin_hash = generate_password_hash('pahlawan140')
    user_hash = generate_password_hash('bps140')
    
    cursor.execute('''
        INSERT OR IGNORE INTO user (username, password_hash, role) 
        VALUES ('admin', ?, 'admin')
    ''', (admin_hash,))
    
    cursor.execute('''
        INSERT OR IGNORE INTO user (username, password_hash, role) 
        VALUES ('user', ?, 'user')
    ''', (user_hash,))
    
    print("✅ Database tables created successfully!")

if __name__ == '__main__':
    db_path = fix_database_access()
    if db_path:
        print(f"\n🎉 Database ready at: {db_path}")
        print("\nNext steps:")
        print("1. Update your config.py with the correct database path")
        print("2. Restart your Flask application")
        print("3. Try accessing the recap and export features")
    else:
        print("\n❌ Failed to fix database access")
