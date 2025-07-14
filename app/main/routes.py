from flask import render_template, request, redirect, url_for, session, send_file, current_app
from app.main import bp
from app.models import Keluarga, Individu
from app import db
from datetime import datetime
from functools import wraps
import pandas as pd
import tempfile
import traceback
import sqlite3
from pathlib import Path

def login_required(f):
    """Decorator to require login for protected routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('auth.login'))
        
        # Check session timeout
        if 'last_activity' in session:
            try:
                last_activity = datetime.fromisoformat(session['last_activity'])
                timeout = current_app.config['SESSION_TIMEOUT']
                if (datetime.now() - last_activity).total_seconds() > timeout:
                    session.clear()
                    return redirect(url_for('auth.login', message='Session expired'))
            except Exception as e:
                current_app.logger.error(f"Session timeout check error: {e}")
        
        # Update last activity
        session['last_activity'] = datetime.now().isoformat()
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role for protected routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            return redirect(url_for('main.dashboard', error='Admin access required'))
        return f(*args, **kwargs)
    return decorated_function

def get_database_stats():
    """Get database statistics with error handling"""
    try:
        # Try using SQLAlchemy first
        total_families = Keluarga.query.count()
        total_individuals = Individu.query.count()
        
        # Get data by dusun
        dusun_stats = db.session.query(
            Keluarga.dusun,
            db.func.count(Keluarga.id).label('jumlah_keluarga'),
            db.func.sum(Keluarga.jumlah_anggota).label('total_anggota'),
            db.func.sum(Keluarga.jumlah_anggota_15plus).label('total_anggota_15plus')
        ).group_by(Keluarga.dusun).all()
        
        # Get data by RT/RW
        rt_rw_stats = db.session.query(
            Keluarga.rt,
            Keluarga.rw,
            db.func.count(Keluarga.id).label('jumlah_keluarga'),
            db.func.sum(Keluarga.jumlah_anggota).label('total_anggota')
        ).group_by(Keluarga.rt, Keluarga.rw).order_by(Keluarga.rt, Keluarga.rw).all()
        
        # Get employment statistics
        employment_stats = db.session.query(
            Individu.memiliki_pekerjaan,
            db.func.count(Individu.id).label('jumlah')
        ).group_by(Individu.memiliki_pekerjaan).all()
        
        # Get education statistics
        education_stats = db.session.query(
            Individu.pendidikan_terakhir,
            db.func.count(Individu.id).label('jumlah')
        ).group_by(Individu.pendidikan_terakhir).all()
        
        # Get pencacah statistics
        pencacah_stats = db.session.query(
            Keluarga.nama_pencacah,
            db.func.count(Keluarga.id).label('jumlah_keluarga'),
            db.func.sum(Keluarga.jumlah_anggota).label('total_anggota'),
            db.func.sum(Keluarga.jumlah_anggota_15plus).label('total_anggota_15plus')
        ).group_by(Keluarga.nama_pencacah).order_by(db.func.count(Keluarga.id).desc()).all()
        
        # Get recent entries (last 10)
        recent_families = Keluarga.query.order_by(Keluarga.created_at.desc()).limit(10).all()
        
        return {
            'total_families': total_families,
            'total_individuals': total_individuals,
            'dusun_stats': dusun_stats,
            'rt_rw_stats': rt_rw_stats,
            'employment_stats': employment_stats,
            'education_stats': education_stats,
            'pencacah_stats': pencacah_stats,
            'recent_families': recent_families
        }
        
    except Exception as e:
        current_app.logger.error(f"SQLAlchemy query failed: {e}")
        
        # Fallback to direct SQLite connection
        try:
            return get_database_stats_direct()
        except Exception as e2:
            current_app.logger.error(f"Direct SQLite query also failed: {e2}")
            raise e2

def get_database_stats_direct():
    """Get database statistics using direct SQLite connection"""
    # Get database path from config
    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
    else:
        raise Exception("Only SQLite databases are supported for direct access")
    
    # Check if database file exists
    if not Path(db_path).exists():
        raise Exception(f"Database file not found: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    cursor = conn.cursor()
    
    try:
        # Get total counts
        cursor.execute("SELECT COUNT(*) as count FROM keluarga")
        total_families = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM individu")
        total_individuals = cursor.fetchone()['count']
        
        # Get data by dusun
        cursor.execute("""
            SELECT dusun, 
                   COUNT(id) as jumlah_keluarga,
                   SUM(jumlah_anggota) as total_anggota,
                   SUM(jumlah_anggota_15plus) as total_anggota_15plus
            FROM keluarga 
            GROUP BY dusun
        """)
        dusun_stats = cursor.fetchall()
        
        # Get data by RT/RW
        cursor.execute("""
            SELECT rt, rw,
                   COUNT(id) as jumlah_keluarga,
                   SUM(jumlah_anggota) as total_anggota
            FROM keluarga 
            GROUP BY rt, rw 
            ORDER BY rt, rw
        """)
        rt_rw_stats = cursor.fetchall()
        
        # Get employment statistics
        cursor.execute("""
            SELECT memiliki_pekerjaan,
                   COUNT(id) as jumlah
            FROM individu 
            GROUP BY memiliki_pekerjaan
        """)
        employment_stats = cursor.fetchall()
        
        # Get education statistics
        cursor.execute("""
            SELECT pendidikan_terakhir,
                   COUNT(id) as jumlah
            FROM individu 
            GROUP BY pendidikan_terakhir
        """)
        education_stats = cursor.fetchall()
        
        # Get pencacah statistics
        cursor.execute("""
            SELECT nama_pencacah,
                   COUNT(id) as jumlah_keluarga,
                   SUM(jumlah_anggota) as total_anggota,
                   SUM(jumlah_anggota_15plus) as total_anggota_15plus
            FROM keluarga 
            WHERE nama_pencacah IS NOT NULL AND nama_pencacah != ''
            GROUP BY nama_pencacah
            ORDER BY COUNT(id) DESC
        """)
        pencacah_stats = cursor.fetchall()
        
        # Get recent entries
        cursor.execute("""
            SELECT * FROM keluarga 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        recent_families_raw = cursor.fetchall()
        
        # Convert to objects for template compatibility
        recent_families = []
        for row in recent_families_raw:
            family = type('Family', (), {})()
            for key in row.keys():
                setattr(family, key, row[key])
            recent_families.append(family)
        
        conn.close()
        
        return {
            'total_families': total_families,
            'total_individuals': total_individuals,
            'dusun_stats': dusun_stats,
            'rt_rw_stats': rt_rw_stats,
            'employment_stats': employment_stats,
            'education_stats': education_stats,
            'pencacah_stats': pencacah_stats,
            'recent_families': recent_families
        }
        
    except Exception as e:
        conn.close()
        raise e

@bp.route('/')
def home():
    return redirect(url_for('auth.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    success = request.args.get('success')
    error = request.args.get('error')
    return render_template('main/dashboard.html', success=success, error=error)

@bp.route('/list-families')
@login_required
def list_families():
    """Route to list all families for editing"""
    try:
        # Get all families with their members
        families = Keluarga.query.order_by(Keluarga.created_at.desc()).all()
        
        # Calculate total individuals
        total_individuals = Individu.query.count()
        
        success = request.args.get('success')
        error = request.args.get('error')
        
        return render_template('main/list-families.html', 
                             families=families, 
                             total_individuals=total_individuals,
                             success=success, 
                             error=error)
                             
    except Exception as e:
        current_app.logger.error(f"Error in list_families route: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.dashboard', error=f'Error loading families: {str(e)}'))

@bp.route('/edit-family-db/<int:family_id>')
@login_required
def edit_family_db(family_id):
    """Route to edit family data from database"""
    try:
        # Get family data
        family = Keluarga.query.get_or_404(family_id)
        
        # Get all members
        members = Individu.query.filter_by(keluarga_id=family.id).order_by(Individu.anggota_ke).all()
        
        # Convert to session format for compatibility with existing templates
        keluarga_data = {
            'keluarga_id': family.keluarga_id,
            'rt': family.rt,
            'rw': family.rw,
            'dusun': family.dusun,
            'nama_kepala': family.nama_kepala,
            'alamat': family.alamat,
            'jumlah_anggota': family.jumlah_anggota,
            'jumlah_anggota_15plus': family.jumlah_anggota_15plus,
            'original_jumlah_anggota_15plus': family.jumlah_anggota_15plus,
            'anggota_count': len(members),
            'timestamp': family.created_at.strftime("%d-%m-%Y %H:%M:%S") if family.created_at else '',
            'all_members_data': [],
            'nama_pencacah': family.nama_pencacah or '',
            'hp_pencacah': family.hp_pencacah or '',
            'tanggal_pencacah': family.tanggal_pencacah or '',
            'nama_pemberi_jawaban': family.nama_pemberi_jawaban or '',
            'hp_pemberi_jawaban': family.hp_pemberi_jawaban or '',
            'tanggal_pemberi_jawaban': family.tanggal_pemberi_jawaban or '',
            'catatan': family.catatan or '',
            'db_id': family.id  # Store database ID for updates
        }
        
        # Convert members to session format
        for member in members:
            member_data = {
                'anggota_ke': member.anggota_ke,
                'nama_anggota': member.nama_anggota,
                'umur': member.umur,
                'hubungan_kepala': member.hubungan_kepala,
                'jenis_kelamin': member.jenis_kelamin,
                'status_perkawinan': member.status_perkawinan,
                'pendidikan_terakhir': member.pendidikan_terakhir,
                'kegiatan_sehari': member.kegiatan_sehari,
                'memiliki_pekerjaan': member.memiliki_pekerjaan,
                'status_pekerjaan_diinginkan': member.status_pekerjaan_diinginkan or '',
                'bidang_usaha_diminati': member.bidang_usaha_diminati or '',
                'bidang_pekerjaan': member.bidang_pekerjaan or '',
                'memiliki_lebih_satu_pekerjaan': member.memiliki_lebih_satu_pekerjaan or '',
                'status_pekerjaan_utama': member.status_pekerjaan_utama or '',
                'pemasaran_usaha_utama': member.pemasaran_usaha_utama or '',
                'penjualan_marketplace_utama': member.penjualan_marketplace_utama or '',
                'bidang_pekerjaan_sampingan1': member.bidang_pekerjaan_sampingan1 or '',
                'status_pekerjaan_sampingan1': member.status_pekerjaan_sampingan1 or '',
                'pemasaran_usaha_sampingan1': member.pemasaran_usaha_sampingan1 or '',
                'penjualan_marketplace_sampingan1': member.penjualan_marketplace_sampingan1 or '',
                'bidang_pekerjaan_sampingan2': member.bidang_pekerjaan_sampingan2 or '',
                'status_pekerjaan_sampingan2': member.status_pekerjaan_sampingan2 or '',
                'pemasaran_usaha_sampingan2': member.pemasaran_usaha_sampingan2 or '',
                'penjualan_marketplace_sampingan2': member.penjualan_marketplace_sampingan2 or '',
                'db_id': member.id  # Store database ID for updates
            }
            keluarga_data['all_members_data'].append(member_data)
        
        # Store in session for editing
        session['keluarga_data'] = keluarga_data
        session['editing_existing'] = True  # Flag to indicate we're editing existing data
        
        success = request.args.get('success')
        error = request.args.get('error')
        
        return render_template('main/final.html', keluarga_data=keluarga_data, success=success, error=error)
        
    except Exception as e:
        current_app.logger.error(f"Error in edit_family_db route: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.list_families', error=f'Error loading family data: {str(e)}'))

@bp.route('/delete-family/<int:family_id>', methods=['POST'])
@login_required
@admin_required
def delete_family(family_id):
    """Route to delete family and all its members"""
    try:
        # Get family data
        family = Keluarga.query.get_or_404(family_id)
        family_name = family.nama_kepala
        
        # Delete all members first (due to foreign key constraint)
        Individu.query.filter_by(keluarga_id=family.id).delete()
        
        # Delete family
        db.session.delete(family)
        db.session.commit()
        
        return redirect(url_for('main.list_families', success=f'Data keluarga {family_name} berhasil dihapus'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in delete_family route: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.list_families', error=f'Error deleting family: {str(e)}'))

@bp.route('/update-family-db', methods=['POST'])
@login_required
def update_family_db():
    """Route to update existing family data in database"""
    try:
        if 'keluarga_data' not in session or not session.get('editing_existing'):
            return redirect(url_for('main.list_families', error='Data keluarga tidak ditemukan'))

        keluarga_data = session['keluarga_data']
        
        # Get surveyor and respondent information from form
        nama_pencacah = request.form.get('nama_pencacah', '').strip()
        hp_pencacah = request.form.get('hp_pencacah', '').strip()
        nama_pemberi_jawaban = request.form.get('nama_pemberi_jawaban', '').strip()
        hp_pemberi_jawaban = request.form.get('hp_pemberi_jawaban', '').strip()
        catatan = request.form.get('catatan', '').strip()
        
        # Validate required fields
        if not all([nama_pencacah, hp_pencacah, nama_pemberi_jawaban, hp_pemberi_jawaban]):
            return redirect(url_for('main.edit_family_db', family_id=keluarga_data['db_id'], error='Nama dan HP pencacah serta pemberi jawaban harus diisi'))
        
        # Set current timestamp for update
        current_timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        
        # Update Keluarga record
        family = Keluarga.query.get(keluarga_data['db_id'])
        if not family:
            return redirect(url_for('main.list_families', error='Data keluarga tidak ditemukan'))
        
        # Update family data including surveyor information
        family.rt = keluarga_data['rt']
        family.rw = keluarga_data['rw']
        family.dusun = keluarga_data['dusun']
        family.nama_kepala = keluarga_data['nama_kepala']
        family.alamat = keluarga_data['alamat']
        family.jumlah_anggota = keluarga_data['jumlah_anggota']
        family.jumlah_anggota_15plus = len(keluarga_data.get('all_members_data', []))
        
        # Update surveyor information (can be changed)
        family.nama_pencacah = nama_pencacah
        family.hp_pencacah = hp_pencacah
        family.nama_pemberi_jawaban = nama_pemberi_jawaban
        family.hp_pemberi_jawaban = hp_pemberi_jawaban
        family.catatan = catatan
        
        # Keep original timestamps but add update timestamp
        family.updated_at = datetime.utcnow()
        
        # Delete existing members
        Individu.query.filter_by(keluarga_id=family.id).delete()
        
        # Create new Individu records
        members_updated = 0
        for member_data in keluarga_data.get('all_members_data', []):
            individu = Individu(
                keluarga_id=family.id,
                anggota_ke=member_data.get('anggota_ke', 1),
                nama_anggota=member_data.get('nama_anggota', ''),
                umur=member_data.get('umur', 0),
                hubungan_kepala=member_data.get('hubungan_kepala', ''),
                jenis_kelamin=member_data.get('jenis_kelamin', ''),
                status_perkawinan=member_data.get('status_perkawinan', ''),
                pendidikan_terakhir=member_data.get('pendidikan_terakhir', ''),
                kegiatan_sehari=member_data.get('kegiatan_sehari', ''),
                memiliki_pekerjaan=member_data.get('memiliki_pekerjaan', ''),
                status_pekerjaan_diinginkan=member_data.get('status_pekerjaan_diinginkan', ''),
                bidang_usaha_diminati=member_data.get('bidang_usaha_diminati', ''),
                bidang_pekerjaan=member_data.get('bidang_pekerjaan', ''),
                memiliki_lebih_satu_pekerjaan=member_data.get('memiliki_lebih_satu_pekerjaan', ''),
                status_pekerjaan_utama=member_data.get('status_pekerjaan_utama', ''),
                pemasaran_usaha_utama=member_data.get('pemasaran_usaha_utama', ''),
                penjualan_marketplace_utama=member_data.get('penjualan_marketplace_utama', ''),
                bidang_pekerjaan_sampingan1=member_data.get('bidang_pekerjaan_sampingan1', ''),
                status_pekerjaan_sampingan1=member_data.get('status_pekerjaan_sampingan1', ''),
                pemasaran_usaha_sampingan1=member_data.get('pemasaran_usaha_sampingan1', ''),
                penjualan_marketplace_sampingan1=member_data.get('penjualan_marketplace_sampingan1', ''),
                bidang_pekerjaan_sampingan2=member_data.get('bidang_pekerjaan_sampingan2', ''),
                status_pekerjaan_sampingan2=member_data.get('status_pekerjaan_sampingan2', ''),
                pemasaran_usaha_sampingan2=member_data.get('pemasaran_usaha_sampingan2', ''),
                penjualan_marketplace_sampingan2=member_data.get('penjualan_marketplace_sampingan2', '')
            )
            
            db.session.add(individu)
            members_updated += 1
        
        # Commit all changes
        db.session.commit()

        # Clear session
        session.pop('keluarga_data', None)
        session.pop('individu_data', None)
        session.pop('editing_existing', None)

        return redirect(url_for('main.list_families', success=f'Data keluarga {family.nama_kepala} berhasil diperbarui! Total {members_updated} anggota keluarga diperbarui.'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR in update_family_db: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.list_families', error=f'Error: {str(e)}'))

@bp.route('/add-member')
@login_required
def add_member():
    """Route to add new member to existing family"""
    try:
        if 'keluarga_data' not in session:
            return redirect(url_for('main.index', error='Data keluarga tidak ditemukan'))
        
        keluarga_data = session['keluarga_data']
        current_member_count = len(keluarga_data.get('all_members_data', []))
        required_member_count = keluarga_data.get('original_jumlah_anggota_15plus', keluarga_data.get('jumlah_anggota_15plus', 0))
        
        # Check if we can add more members
        if current_member_count >= required_member_count:
            return redirect(url_for('main.final_page', error='Jumlah anggota sudah sesuai dengan yang ditentukan'))
        
        # Set up for adding new member
        keluarga_data['anggota_count'] = current_member_count
        session['keluarga_data'] = keluarga_data
        
        return redirect(url_for('main.lanjutan', success=f'Silakan tambahkan anggota ke-{current_member_count + 1}'))
        
    except Exception as e:
        current_app.logger.error(f"Error in add_member route: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.final_page', error=f'Error: {str(e)}'))

@bp.route('/delete-member', methods=['POST'])
@login_required
def delete_member():
    """Route to delete a member from family"""
    try:
        if 'keluarga_data' not in session:
            return redirect(url_for('main.final_page', error='Data keluarga tidak ditemukan'))
        
        keluarga_data = session['keluarga_data']
        member_index = int(request.form.get('member_index', -1))
        
        # Validate member index
        if member_index < 0 or member_index >= len(keluarga_data.get('all_members_data', [])):
            return redirect(url_for('main.final_page', error='Index anggota tidak valid'))
        
        # Get member name for success message
        member_name = keluarga_data['all_members_data'][member_index]['nama_anggota']
        
        # Remove member from list
        keluarga_data['all_members_data'].pop(member_index)
        
        # Reorder anggota_ke numbers
        for i, member in enumerate(keluarga_data['all_members_data']):
            member['anggota_ke'] = i + 1
        
        # Update session
        session['keluarga_data'] = keluarga_data
        
        return redirect(url_for('main.final_page', success=f'Anggota {member_name} berhasil dihapus'))
        
    except Exception as e:
        current_app.logger.error(f"Error in delete_member route: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.final_page', error=f'Error: {str(e)}'))

@bp.route('/rekap')
@login_required
def rekap():
    """Route to show database summary/recap"""
    try:
        stats = get_database_stats()
        
        success = request.args.get('success')
        error = request.args.get('error')
        
        return render_template('main/rekap.html',
                             total_families=stats['total_families'],
                             total_individuals=stats['total_individuals'],
                             dusun_stats=stats['dusun_stats'],
                             rt_rw_stats=stats['rt_rw_stats'],
                             employment_stats=stats['employment_stats'],
                             education_stats=stats['education_stats'],
                             recent_families=stats['recent_families'],
                             success=success,
                             error=error,
                             pencacah_stats=stats['pencacah_stats'])
                             
    except Exception as e:
        current_app.logger.error(f"Error in rekap route: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.dashboard', error=f'Error loading recap: {str(e)}'))

@bp.route('/download-excel')
@login_required
@admin_required
def download_excel():
    try:
        # Try SQLAlchemy first
        try:
            keluarga_list = Keluarga.query.all()
        except Exception as e:
            current_app.logger.error(f"SQLAlchemy query failed, trying direct access: {e}")
            # Fallback to direct SQLite access
            keluarga_list = get_families_direct()
        
        if not keluarga_list:
            return redirect(url_for('main.dashboard', error='No data found'))
        
        all_rows = []
        for keluarga in keluarga_list:
            # Handle both SQLAlchemy objects and direct query results
            if hasattr(keluarga, 'anggota'):
                # SQLAlchemy object
                individuals = keluarga.anggota
            else:
                # Direct query result
                individuals = get_individuals_for_family_direct(keluarga.id)
            
            head_row = {
                'Timestamp': getattr(keluarga, 'tanggal_pencacah', '') or '',
                'ID Keluarga': keluarga.keluarga_id,
                'RT': keluarga.rt,
                'RW': keluarga.rw,
                'Dusun': keluarga.dusun,
                'Nama Kepala Keluarga': keluarga.nama_kepala,
                'Alamat': keluarga.alamat,
                'Jumlah Anggota Keluarga': keluarga.jumlah_anggota,
                'Jumlah Anggota Usia 15+': keluarga.jumlah_anggota_15plus,
                'Anggota Ke': 1,
                'Nama Anggota': keluarga.nama_kepala,
                'Umur': '',
                'Hubungan dengan Kepala Keluarga': 'Kepala Keluarga',
                'Jenis Kelamin': '',
                'Status Perkawinan': '',
                'Pendidikan Terakhir': '',
                'Kegiatan Sehari-hari': '',
                'Apakah Memiliki Pekerjaan': '',
                'Status Pekerjaan yang Diinginkan': '',
                'Bidang Usaha yang Diminati': '',
                'Bidang Pekerjaan': '',
                'Status Pekerjaan Utama': '',
                'Pemasaran Usaha Utama': '',
                'Penjualan Marketplace Utama': '',
                'Bidang Pekerjaan Sampingan 1': '',
                'Status Pekerjaan Sampingan 1': '',
                'Pemasaran Usaha Sampingan 1': '',
                'Penjualan Marketplace Sampingan 1': '',
                'Bidang Pekerjaan Sampingan 2': '',
                'Status Pekerjaan Sampingan 2': '',
                'Pemasaran Usaha Sampingan 2': '',
                'Penjualan Marketplace Sampingan 2': '',
                'Memiliki Lebih dari Satu Pekerjaan': '',
                'Nama Pencacah': getattr(keluarga, 'nama_pencacah', '') or '',
                'HP Pencacah': getattr(keluarga, 'hp_pencacah', '') or '',
                'Tanggal Pencacah': getattr(keluarga, 'tanggal_pencacah', '') or '',
                'Nama Pemberi Jawaban': getattr(keluarga, 'nama_pemberi_jawaban', '') or '',
                'HP Pemberi Jawaban': getattr(keluarga, 'hp_pemberi_jawaban', '') or '',
                'Tanggal Pemberi Jawaban': getattr(keluarga, 'tanggal_pemberi_jawaban', '') or '',
                'Catatan': getattr(keluarga, 'catatan', '') or ''
            }
            all_rows.append(head_row)
            
            for individu in individuals:
                member_row = {
                    'Timestamp': getattr(keluarga, 'tanggal_pencacah', '') or '',
                    'ID Keluarga': keluarga.keluarga_id,
                    'RT': keluarga.rt,
                    'RW': keluarga.rw,
                    'Dusun': keluarga.dusun,
                    'Nama Kepala Keluarga': keluarga.nama_kepala,
                    'Alamat': keluarga.alamat,
                    'Jumlah Anggota Keluarga': keluarga.jumlah_anggota,
                    'Jumlah Anggota Usia 15+': keluarga.jumlah_anggota_15plus,
                    'Anggota Ke': getattr(individu, 'anggota_ke', ''),
                    'Nama Anggota': getattr(individu, 'nama_anggota', ''),
                    'Umur': getattr(individu, 'umur', ''),
                    'Hubungan dengan Kepala Keluarga': getattr(individu, 'hubungan_kepala', ''),
                    'Jenis Kelamin': getattr(individu, 'jenis_kelamin', ''),
                    'Status Perkawinan': getattr(individu, 'status_perkawinan', ''),
                    'Pendidikan Terakhir': getattr(individu, 'pendidikan_terakhir', ''),
                    'Kegiatan Sehari-hari': getattr(individu, 'kegiatan_sehari', ''),
                    'Apakah Memiliki Pekerjaan': getattr(individu, 'memiliki_pekerjaan', ''),
                    'Status Pekerjaan yang Diinginkan': getattr(individu, 'status_pekerjaan_diinginkan', '') or '',
                    'Bidang Usaha yang Diminati': getattr(individu, 'bidang_usaha_diminati', '') or '',
                    'Bidang Pekerjaan': getattr(individu, 'bidang_pekerjaan', '') or '',
                    'Status Pekerjaan Utama': getattr(individu, 'status_pekerjaan_utama', '') or '',
                    'Pemasaran Usaha Utama': getattr(individu, 'pemasaran_usaha_utama', '') or '',
                    'Penjualan Marketplace Utama': getattr(individu, 'penjualan_marketplace_utama', '') or '',
                    'Bidang Pekerjaan Sampingan 1': getattr(individu, 'bidang_pekerjaan_sampingan1', '') or '',
                    'Status Pekerjaan Sampingan 1': getattr(individu, 'status_pekerjaan_sampingan1', '') or '',
                    'Pemasaran Usaha Sampingan 1': getattr(individu, 'pemasaran_usaha_sampingan1', '') or '',
                    'Penjualan Marketplace Sampingan 1': getattr(individu, 'penjualan_marketplace_sampingan1', '') or '',
                    'Bidang Pekerjaan Sampingan 2': getattr(individu, 'bidang_pekerjaan_sampingan2', '') or '',
                    'Status Pekerjaan Sampingan 2': getattr(individu, 'status_pekerjaan_sampingan2', '') or '',
                    'Pemasaran Usaha Sampingan 2': getattr(individu, 'pemasaran_usaha_sampingan2', '') or '',
                    'Penjualan Marketplace Sampingan 2': getattr(individu, 'penjualan_marketplace_sampingan2', '') or '',
                    'Memiliki Lebih dari Satu Pekerjaan': getattr(individu, 'memiliki_lebih_satu_pekerjaan', '') or '',
                    'Nama Pencacah': getattr(keluarga, 'nama_pencacah', '') or '',
                    'HP Pencacah': getattr(keluarga, 'hp_pencacah', '') or '',
                    'Tanggal Pencacah': getattr(keluarga, 'tanggal_pencacah', '') or '',
                    'Nama Pemberi Jawaban': getattr(keluarga, 'nama_pemberi_jawaban', '') or '',
                    'HP Pemberi Jawaban': getattr(keluarga, 'hp_pemberi_jawaban', '') or '',
                    'Tanggal Pemberi Jawaban': getattr(keluarga, 'tanggal_pemberi_jawaban', '') or '',
                    'Catatan': getattr(keluarga, 'catatan', '') or ''
                }
                all_rows.append(member_row)
        
        df = pd.DataFrame(all_rows)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            df.to_excel(tmp.name, index=False)
            tmp_path = tmp.name
        
        download_name = f"data_sensus_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        current_app.logger.error(f"ERROR in download_excel: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.dashboard', error=str(e)))

def get_families_direct():
    """Get families using direct SQLite connection"""
    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM keluarga ORDER BY created_at DESC")
    families_raw = cursor.fetchall()
    
    families = []
    for row in families_raw:
        family = type('Family', (), {})()
        for key in row.keys():
            setattr(family, key, row[key])
        families.append(family)
    
    conn.close()
    return families

def get_individuals_for_family_direct(family_id):
    """Get individuals for a family using direct SQLite connection"""
    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM individu WHERE keluarga_id = ? ORDER BY anggota_ke", (family_id,))
    individuals_raw = cursor.fetchall()
    
    individuals = []
    for row in individuals_raw:
        individual = type('Individual', (), {})()
        for key in row.keys():
            setattr(individual, key, row[key])
        individuals.append(individual)
    
    conn.close()
    return individuals

@bp.route('/index')
@login_required
def index():
    success = request.args.get('success')
    error = request.args.get('error')
    clear = request.args.get('clear')
    
    # Clear session if requested
    if clear:
        session.pop('keluarga_data', None)
        session.pop('individu_data', None)
    
    return render_template('main/index.html', success=success, error=error)

@bp.route('/back-to-index')
@login_required
def back_to_index():
    """Route to go back to index and clear session data"""
    session.pop('keluarga_data', None)
    session.pop('individu_data', None)
    return redirect(url_for('main.index', clear='true'))

@bp.route('/edit-keluarga')
@login_required
def edit_keluarga():
    """Route to edit family data"""
    if 'keluarga_data' not in session:
        return redirect(url_for('main.index'))
    
    keluarga_data = session['keluarga_data']
    success = request.args.get('success')
    error = request.args.get('error')
    return render_template('main/edit-keluarga.html', keluarga_data=keluarga_data, success=success, error=error)

@bp.route('/edit-anggota')
@login_required
def edit_anggota():
    """Route to edit member data"""
    if 'keluarga_data' not in session:
        return redirect(url_for('main.index'))
    
    # Get member index from URL parameters
    member_index = request.args.get('memberIndex', type=int)
    if member_index is None:
        return redirect(url_for('main.final_page'))
    
    keluarga_data = session['keluarga_data']
    
    # Validate member index
    if member_index < 0 or member_index >= len(keluarga_data.get('all_members_data', [])):
        return redirect(url_for('main.final_page'))
    
    member_data = keluarga_data['all_members_data'][member_index]
    success = request.args.get('success')
    error = request.args.get('error')
    
    return render_template('main/edit-anggota.html', 
                         keluarga_data=keluarga_data, 
                         member_data=member_data,
                         member_index=member_index,
                         success=success,
                         error=error)

@bp.route('/submit', methods=['POST'])
@login_required
def submit():
    try:
        # Clear any existing session data when starting new family
        session.pop('keluarga_data', None)
        session.pop('individu_data', None)
        
        # Get form data
        rt = request.form.get('rt', '').strip()
        rw = request.form.get('rw', '').strip()
        dusun = request.form.get('dusun', '').strip()
        nama_kepala = request.form.get('nama_kepala', '').strip()
        alamat = request.form.get('alamat', '').strip()
        jumlah_anggota = request.form.get('jumlah_anggota', '').strip()
        jumlah_anggota_15plus = request.form.get('jumlah_anggota_15plus', '').strip()
        
        # Server-side validation
        missing_fields = []
        if not rt:
            missing_fields.append('RT')
        if not rw:
            missing_fields.append('RW')
        if not dusun:
            missing_fields.append('Dusun')
        if not nama_kepala:
            missing_fields.append('Nama Kepala Keluarga')
        if not alamat:
            missing_fields.append('Alamat')
        if not jumlah_anggota:
            missing_fields.append('Jumlah Anggota')
        if not jumlah_anggota_15plus:
            missing_fields.append('Jumlah Anggota 15+')
            
        if missing_fields:
            error_msg = f"Field berikut harus diisi: {', '.join(missing_fields)}"
            return redirect(url_for('main.index', error=error_msg))
        
        # Convert to integers
        try:
            jumlah_anggota_int = int(jumlah_anggota)
            jumlah_anggota_15plus_int = int(jumlah_anggota_15plus)
        except ValueError:
            return redirect(url_for('main.index', error='Jumlah anggota harus berupa angka yang valid'))
        
        # Validate member counts
        if jumlah_anggota_int < 1:
            return redirect(url_for('main.index', error='Jumlah anggota keluarga minimal 1'))
        
        if jumlah_anggota_15plus_int < 0:
            return redirect(url_for('main.index', error='Jumlah anggota usia 15+ tidak boleh negatif'))
            
        if jumlah_anggota_15plus_int > jumlah_anggota_int:
            return redirect(url_for('main.index', error='Jumlah anggota usia 15+ tidak boleh lebih dari jumlah anggota keluarga'))

        # Generate timestamp and ID
        timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        keluarga_id = f"KEL-{rt}{rw}-{datetime.now().strftime('%d%m%Y%H%M%S')}"
        
        # Save basic family data to session
        keluarga_data = {
            'keluarga_id': keluarga_id,
            'rt': rt,
            'rw': rw,
            'dusun': dusun,
            'nama_kepala': nama_kepala,
            'alamat': alamat,
            'jumlah_anggota': jumlah_anggota_int,
            'jumlah_anggota_15plus': jumlah_anggota_15plus_int,
            'original_jumlah_anggota_15plus': jumlah_anggota_15plus_int,
            'anggota_count': 0,
            'timestamp': timestamp,
            'all_members_data': []
        }
        
        session['keluarga_data'] = keluarga_data
        session.permanent = True
        
        # Determine next step
        if jumlah_anggota_15plus_int > 0:
            return redirect(url_for('main.lanjutan', success='Data keluarga berhasil disimpan. Lanjutkan ke input anggota keluarga.'))
        else:
            return redirect(url_for('main.final_page', success='Data keluarga berhasil disimpan. Lanjutkan ke halaman akhir.'))
            
    except Exception as e:
        current_app.logger.error(f"Error in submit route: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.index', error=f'Terjadi kesalahan server: {str(e)}'))

@bp.route('/lanjutan')
@login_required
def lanjutan():
    if 'keluarga_data' not in session:
        return redirect(url_for('main.index'))
    
    keluarga_data = session['keluarga_data']
    success = request.args.get('success')
    error = request.args.get('error')
    return render_template('main/lanjutan.html', keluarga_data=keluarga_data, success=success, error=error)

@bp.route('/pekerjaan')
@login_required
def pekerjaan():
    if 'keluarga_data' not in session or 'individu_data' not in session:
        return redirect(url_for('main.index'))
    
    keluarga_data = session['keluarga_data']
    individu_data = session['individu_data']
    success = request.args.get('success')
    error = request.args.get('error')
    return render_template('main/pekerjaan.html', keluarga_data=keluarga_data, individu_data=individu_data, success=success, error=error)

@bp.route('/final')
@login_required
def final_page():
    if 'keluarga_data' not in session:
        return redirect(url_for('main.index', error='Data keluarga tidak ditemukan. Silakan mulai dari awal.'))
    
    keluarga_data = session['keluarga_data']
    success = request.args.get('success')
    error = request.args.get('error')
    
    # Log for debugging
    current_app.logger.info(f"Final page - keluarga_data: {keluarga_data}")
    current_app.logger.info(f"Final page - members count: {len(keluarga_data.get('all_members_data', []))}")
    
    return render_template('main/final.html', keluarga_data=keluarga_data, success=success, error=error)

@bp.route('/submit-individu', methods=['POST'])
@login_required
def submit_individu():
    try:
        if 'keluarga_data' not in session:
            return redirect(url_for('main.index', error='Data keluarga tidak ditemukan'))
        
        keluarga_data = session['keluarga_data']
        
        # Collect individual data from form
        nama_anggota = request.form.get('nama')
        umur = request.form.get('umur')
        hubungan_kepala = request.form.get('hubungan')
        jenis_kelamin = request.form.get('jenis_kelamin')
        status_perkawinan = request.form.get('status_perkawinan')
        pendidikan_terakhir = request.form.get('pendidikan')
        kegiatan_sehari = request.form.get('kegiatan')
        memiliki_pekerjaan = request.form.get('memiliki_pekerjaan')
        status_pekerjaan_diinginkan = request.form.get('status_pekerjaan_diinginkan')
        bidang_usaha_diminati = request.form.get('bidang_usaha')
        
        # Validate individual data
        required_fields = [nama_anggota, umur, hubungan_kepala, jenis_kelamin, status_perkawinan, pendidikan_terakhir, kegiatan_sehari, memiliki_pekerjaan]
        if not all(required_fields):
            return redirect(url_for('main.lanjutan', error='Semua field harus diisi'))
        
        try:
            umur_int = int(umur)
        except ValueError:
            return redirect(url_for('main.lanjutan', error='Usia harus berupa angka'))
        
        if umur_int < 15:
            return redirect(url_for('main.lanjutan', error='Usia anggota keluarga harus 15 tahun atau lebih'))
        
        # Create individual data
        individu_data = {
            'anggota_ke': keluarga_data['anggota_count'] + 1,
            'nama_anggota': nama_anggota,
            'umur': umur_int,
            'hubungan_kepala': hubungan_kepala,
            'jenis_kelamin': jenis_kelamin,
            'status_perkawinan': status_perkawinan,
            'pendidikan_terakhir': pendidikan_terakhir,
            'kegiatan_sehari': kegiatan_sehari,
            'memiliki_pekerjaan': memiliki_pekerjaan,
            'status_pekerjaan_diinginkan': status_pekerjaan_diinginkan or '',
            'bidang_usaha_diminati': bidang_usaha_diminati or ''
        }
        
        session['individu_data'] = individu_data
        
        # Determine next step based on employment status
        if memiliki_pekerjaan == 'Ya':
            return redirect(url_for('main.pekerjaan', success='Data anggota berhasil disimpan. Lanjutkan ke data pekerjaan.'))
        else:
            # Save individual data to session and continue
            keluarga_data['all_members_data'].append(individu_data)
            keluarga_data['anggota_count'] += 1
            session['keluarga_data'] = keluarga_data
            session.pop('individu_data', None)
            
            # Check if we need more members
            required_member_count = keluarga_data.get('original_jumlah_anggota_15plus', keluarga_data.get('jumlah_anggota_15plus', 0))
            if keluarga_data['anggota_count'] < required_member_count:
                return redirect(url_for('main.lanjutan', success=f'Data anggota ke-{keluarga_data["anggota_count"]} berhasil disimpan. Lanjutkan ke anggota berikutnya.'))
            else:
                return redirect(url_for('main.final_page', success='Semua data anggota berhasil disimpan. Periksa data sebelum menyimpan.'))
    
    except Exception as e:
        current_app.logger.error(f"Error in submit_individu: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.lanjutan', error=f'Terjadi kesalahan: {str(e)}'))

@bp.route('/submit-pekerjaan', methods=['POST'])
@login_required
def submit_pekerjaan():
    try:
        if 'keluarga_data' not in session or 'individu_data' not in session:
            return redirect(url_for('main.index', error='Data tidak ditemukan'))
        
        keluarga_data = session['keluarga_data']
        individu_data = session['individu_data']
        
        # Get employment data
        bidang_pekerjaan = request.form.get('bidang_pekerjaan')
        status_pekerjaan_utama = request.form.get('status_pekerjaan_utama')
        pemasaran_usaha_utama = request.form.get('pemasaran_usaha_utama', '')
        penjualan_marketplace_utama = request.form.get('penjualan_marketplace_utama', '')
        memiliki_lebih_satu_pekerjaan = request.form.get('memiliki_lebih_satu_pekerjaan')
        
        # Validate required fields
        if not bidang_pekerjaan or not status_pekerjaan_utama or not memiliki_lebih_satu_pekerjaan:
            return redirect(url_for('main.pekerjaan', error='Semua field yang wajib harus diisi'))
        
        # Update individual data with employment info
        individu_data.update({
            'bidang_pekerjaan': bidang_pekerjaan,
            'status_pekerjaan_utama': status_pekerjaan_utama,
            'pemasaran_usaha_utama': pemasaran_usaha_utama,
            'penjualan_marketplace_utama': penjualan_marketplace_utama,
            'memiliki_lebih_satu_pekerjaan': memiliki_lebih_satu_pekerjaan
        })
        
        # Handle additional jobs if applicable
        if memiliki_lebih_satu_pekerjaan == 'Ya':
            # Get additional job data
            bidang_pekerjaan_sampingan1 = request.form.get('bidang_pekerjaan_sampingan1', '')
            status_pekerjaan_sampingan1 = request.form.get('status_pekerjaan_sampingan1', '')
            pemasaran_usaha_sampingan1 = request.form.get('pemasaran_usaha_sampingan1', '')
            penjualan_marketplace_sampingan1 = request.form.get('penjualan_marketplace_sampingan1', '')
            
            bidang_pekerjaan_sampingan2 = request.form.get('bidang_pekerjaan_sampingan2', '')
            status_pekerjaan_sampingan2 = request.form.get('status_pekerjaan_sampingan2', '')
            pemasaran_usaha_sampingan2 = request.form.get('pemasaran_usaha_sampingan2', '')
            penjualan_marketplace_sampingan2 = request.form.get('penjualan_marketplace_sampingan2', '')
            
            individu_data.update({
                'bidang_pekerjaan_sampingan1': bidang_pekerjaan_sampingan1,
                'status_pekerjaan_sampingan1': status_pekerjaan_sampingan1,
                'pemasaran_usaha_sampingan1': pemasaran_usaha_sampingan1,
                'penjualan_marketplace_sampingan1': penjualan_marketplace_sampingan1,
                'bidang_pekerjaan_sampingan2': bidang_pekerjaan_sampingan2,
                'status_pekerjaan_sampingan2': status_pekerjaan_sampingan2,
                'pemasaran_usaha_sampingan2': pemasaran_usaha_sampingan2,
                'penjualan_marketplace_sampingan2': penjualan_marketplace_sampingan2
            })
        else:
            # Set empty values for additional jobs
            individu_data.update({
                'bidang_pekerjaan_sampingan1': '',
                'status_pekerjaan_sampingan1': '',
                'pemasaran_usaha_sampingan1': '',
                'penjualan_marketplace_sampingan1': '',
                'bidang_pekerjaan_sampingan2': '',
                'status_pekerjaan_sampingan2': '',
                'pemasaran_usaha_sampingan2': '',
                'penjualan_marketplace_sampingan2': ''
            })

        # Add completed individual data to family data
        keluarga_data['all_members_data'].append(individu_data)
        keluarga_data['anggota_count'] += 1
        session['keluarga_data'] = keluarga_data
        session.pop('individu_data', None)
        
        # Check if we need more members
        required_member_count = keluarga_data.get('original_jumlah_anggota_15plus', keluarga_data.get('jumlah_anggota_15plus', 0))
        if keluarga_data['anggota_count'] < required_member_count:
            return redirect(url_for('main.lanjutan', success=f'Data anggota ke-{keluarga_data["anggota_count"]} berhasil disimpan. Lanjutkan ke anggota berikutnya.'))
        else:
            return redirect(url_for('main.final_page', success='Semua data anggota berhasil disimpan. Lanjutkan ke halaman akhir.'))

    except Exception as e:
        current_app.logger.error(f"Error in submit_pekerjaan: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.pekerjaan', error=f'Terjadi kesalahan: {str(e)}'))

@bp.route('/submit-final', methods=['POST'])
@login_required
def submit_final():
    try:
        if 'keluarga_data' not in session:
            return redirect(url_for('main.index', error='Data keluarga tidak ditemukan'))
        
        keluarga_data = session['keluarga_data']
        
        # Validate member count before saving
        current_member_count = len(keluarga_data.get('all_members_data', []))
        required_member_count = keluarga_data.get('original_jumlah_anggota_15plus', keluarga_data.get('jumlah_anggota_15plus', 0))
        
        if current_member_count != required_member_count:
            return redirect(url_for('main.final_page', error=f'Jumlah anggota tidak sesuai. Saat ini: {current_member_count}, dibutuhkan: {required_member_count}'))
        
        # Get surveyor information
        nama_pencacah = request.form.get('nama_pencacah', '').strip()
        hp_pencacah = request.form.get('hp_pencacah', '').strip()
        nama_pemberi_jawaban = request.form.get('nama_pemberi_jawaban', '').strip()
        hp_pemberi_jawaban = request.form.get('hp_pemberi_jawaban', '').strip()
        catatan = request.form.get('catatan', '').strip()
        
        # Validate required fields
        if not nama_pencacah or not hp_pencacah or not nama_pemberi_jawaban or not hp_pemberi_jawaban:
            return redirect(url_for('main.final_page', error='Nama dan HP pencacah serta pemberi jawaban harus diisi'))
        
        # Set current timestamp
        current_timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        
        # Create Keluarga record
        keluarga = Keluarga(
            keluarga_id=keluarga_data['keluarga_id'],
            rt=keluarga_data['rt'],
            rw=keluarga_data['rw'],
            dusun=keluarga_data['dusun'],
            nama_kepala=keluarga_data['nama_kepala'],
            alamat=keluarga_data['alamat'],
            jumlah_anggota=keluarga_data['jumlah_anggota'],
            jumlah_anggota_15plus=len(keluarga_data.get('all_members_data', [])),
            nama_pencacah=nama_pencacah,
            hp_pencacah=hp_pencacah,
            tanggal_pencacah=current_timestamp,
            nama_pemberi_jawaban=nama_pemberi_jawaban,
            hp_pemberi_jawaban=hp_pemberi_jawaban,
            tanggal_pemberi_jawaban=current_timestamp,
            catatan=catatan
        )
        
        db.session.add(keluarga)
        db.session.flush()  # Get the ID
        
        # Create Individu records
        members_saved = 0
        for member_data in keluarga_data.get('all_members_data', []):
            individu = Individu(
                keluarga_id=keluarga.id,
                anggota_ke=member_data.get('anggota_ke', 1),
                nama_anggota=member_data.get('nama_anggota', ''),
                umur=member_data.get('umur', 0),
                hubungan_kepala=member_data.get('hubungan_kepala', ''),
                jenis_kelamin=member_data.get('jenis_kelamin', ''),
                status_perkawinan=member_data.get('status_perkawinan', ''),
                pendidikan_terakhir=member_data.get('pendidikan_terakhir', ''),
                kegiatan_sehari=member_data.get('kegiatan_sehari', ''),
                memiliki_pekerjaan=member_data.get('memiliki_pekerjaan', ''),
                status_pekerjaan_diinginkan=member_data.get('status_pekerjaan_diinginkan', ''),
                bidang_usaha_diminati=member_data.get('bidang_usaha_diminati', ''),
                bidang_pekerjaan=member_data.get('bidang_pekerjaan', ''),
                memiliki_lebih_satu_pekerjaan=member_data.get('memiliki_lebih_satu_pekerjaan', ''),
                status_pekerjaan_utama=member_data.get('status_pekerjaan_utama', ''),
                pemasaran_usaha_utama=member_data.get('pemasaran_usaha_utama', ''),
                penjualan_marketplace_utama=member_data.get('penjualan_marketplace_utama', ''),
                bidang_pekerjaan_sampingan1=member_data.get('bidang_pekerjaan_sampingan1', ''),
                status_pekerjaan_sampingan1=member_data.get('status_pekerjaan_sampingan1', ''),
                pemasaran_usaha_sampingan1=member_data.get('pemasaran_usaha_sampingan1', ''),
                penjualan_marketplace_sampingan1=member_data.get('penjualan_marketplace_sampingan1', ''),
                bidang_pekerjaan_sampingan2=member_data.get('bidang_pekerjaan_sampingan2', ''),
                status_pekerjaan_sampingan2=member_data.get('status_pekerjaan_sampingan2', ''),
                pemasaran_usaha_sampingan2=member_data.get('pemasaran_usaha_sampingan2', ''),
                penjualan_marketplace_sampingan2=member_data.get('penjualan_marketplace_sampingan2', '')
            )
            
            db.session.add(individu)
            members_saved += 1
        
        # Commit all changes
        db.session.commit()

        # Clear session
        session.pop('keluarga_data', None)
        session.pop('individu_data', None)

        return redirect(url_for('main.dashboard', success=f'Data keluarga {keluarga.nama_kepala} berhasil disimpan! Total {members_saved} anggota keluarga tersimpan.'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"ERROR in submit_final: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.final_page', error=f'Error: {str(e)}'))

@bp.route('/edit-member', methods=['POST'])
@login_required
def edit_member():
    try:
        if 'keluarga_data' not in session:
            return redirect(url_for('main.final_page', error='Data keluarga tidak ditemukan'))

        keluarga_data = session['keluarga_data']
        
        # Debug: Log all form data
        current_app.logger.info(f"Form data received: {dict(request.form)}")
        
        # Get member index from form
        member_index = int(request.form.get('memberIndex'))
        
        current_app.logger.info(f"Editing member at index: {member_index}")
        
        if member_index < 0 or member_index >= len(keluarga_data['all_members_data']):
            return redirect(url_for('main.final_page', error='Index anggota tidak valid'))

        # Update member data
        member_data = keluarga_data['all_members_data'][member_index]
        
        current_app.logger.info(f"Original member data: {member_data}")
        
        # Update basic info
        member_data['nama_anggota'] = request.form.get('nama_anggota', '').strip()
        member_data['umur'] = int(request.form.get('umur', 0))
        member_data['jenis_kelamin'] = request.form.get('jenis_kelamin', '').strip()
        member_data['hubungan_kepala'] = request.form.get('hubungan_kepala', '').strip()
        member_data['status_perkawinan'] = request.form.get('status_perkawinan', '').strip()
        member_data['pendidikan_terakhir'] = request.form.get('pendidikan_terakhir', '').strip()
        member_data['kegiatan_sehari'] = request.form.get('kegiatan_sehari', '').strip()
        member_data['memiliki_pekerjaan'] = request.form.get('memiliki_pekerjaan', '').strip()

        # Update job-related fields based on memiliki_pekerjaan
        if member_data['memiliki_pekerjaan'] == 'Tidak':
            # Clear job fields and update no-job fields
            member_data.update({
                'status_pekerjaan_diinginkan': request.form.get('status_pekerjaan_diinginkan', '').strip(),
                'bidang_usaha_diminati': request.form.get('bidang_usaha_diminati', '').strip(),
                'bidang_pekerjaan': '',
                'memiliki_lebih_satu_pekerjaan': '',
                'status_pekerjaan_utama': '',
                'pemasaran_usaha_utama': '',
                'penjualan_marketplace_utama': '',
                'bidang_pekerjaan_sampingan1': '',
                'status_pekerjaan_sampingan1': '',
                'pemasaran_usaha_sampingan1': '',
                'penjualan_marketplace_sampingan1': '',
                'bidang_pekerjaan_sampingan2': '',
                'status_pekerjaan_sampingan2': '',
                'pemasaran_usaha_sampingan2': '',
                'penjualan_marketplace_sampingan2': '',
            })
        else:
            # Update job fields
            member_data.update({
                'status_pekerjaan_diinginkan': '',
                'bidang_usaha_diminati': '',
                'bidang_pekerjaan': request.form.get('bidang_pekerjaan', '').strip(),
                'memiliki_lebih_satu_pekerjaan': request.form.get('memiliki_lebih_satu_pekerjaan', 'Tidak').strip(),
                'status_pekerjaan_utama': request.form.get('status_pekerjaan_utama', '').strip(),
                'pemasaran_usaha_utama': request.form.get('pemasaran_usaha_utama', '').strip(),
                'penjualan_marketplace_utama': request.form.get('penjualan_marketplace_utama', '').strip(),
                'bidang_pekerjaan_sampingan1': request.form.get('bidang_pekerjaan_sampingan1', '').strip(),
                'status_pekerjaan_sampingan1': request.form.get('status_pekerjaan_sampingan1', '').strip(),
                'pemasaran_usaha_sampingan1': request.form.get('pemasaran_usaha_sampingan1', '').strip(),
                'penjualan_marketplace_sampingan1': request.form.get('penjualan_marketplace_sampingan1', '').strip(),
                'bidang_pekerjaan_sampingan2': request.form.get('bidang_pekerjaan_sampingan2', '').strip(),
                'status_pekerjaan_sampingan2': request.form.get('status_pekerjaan_sampingan2', '').strip(),
                'pemasaran_usaha_sampingan2': request.form.get('pemasaran_usaha_sampingan2', '').strip(),
                'penjualan_marketplace_sampingan2': request.form.get('penjualan_marketplace_sampingan2', '').strip(),
            })

        current_app.logger.info(f"Updated member data: {member_data}")

        # Update session with modified data
        keluarga_data['all_members_data'][member_index] = member_data
        session['keluarga_data'] = keluarga_data
        session['modified'] = True
        
        current_app.logger.info(f"Session updated successfully")

        return redirect(url_for('main.final_page', success='Data anggota berhasil diperbarui'))

    except Exception as e:
        current_app.logger.error(f"ERROR in edit_member: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.final_page', error=f'Error: {str(e)}'))

@bp.route('/edit-family', methods=['POST'])
@login_required
def edit_family():
    try:
        if 'keluarga_data' not in session:
            return redirect(url_for('main.index', error='Data keluarga tidak ditemukan'))

        keluarga_data = session['keluarga_data']
        
        # Debug: Log all form data
        current_app.logger.info(f"Form data received: {dict(request.form)}")
        current_app.logger.info(f"Original keluarga data: {keluarga_data}")
        
        # Get current member count
        current_member_count = len(keluarga_data.get('all_members_data', []))
        
        # Update family data
        keluarga_data['dusun'] = request.form.get('dusun', '').strip()
        keluarga_data['rt'] = request.form.get('rt', '').strip()
        keluarga_data['rw'] = request.form.get('rw', '').strip()
        keluarga_data['nama_kepala'] = request.form.get('nama_kepala', '').strip()
        keluarga_data['alamat'] = request.form.get('alamat', '').strip()
        keluarga_data['jumlah_anggota'] = int(request.form.get('jumlah_anggota', 0))
        
        # Handle member count changes
        new_member_count = int(request.form.get('jumlah_anggota_15plus', 0))
        
        current_app.logger.info(f"Current member count: {current_member_count}, New member count: {new_member_count}")
        
        if new_member_count < current_member_count:
            # Remove excess members
            keluarga_data['all_members_data'] = keluarga_data['all_members_data'][:new_member_count]
        elif new_member_count > current_member_count:
            # Set up for adding new members
            keluarga_data['jumlah_anggota_15plus'] = new_member_count - current_member_count
            keluarga_data['anggota_count'] = current_member_count
        
        # Update original count
        keluarga_data['original_jumlah_anggota_15plus'] = new_member_count

        current_app.logger.info(f"Updated keluarga data: {keluarga_data}")

        # Update session with modified data
        session['keluarga_data'] = keluarga_data
        session['modified'] = True
        
        current_app.logger.info(f"Session updated successfully")

        # Check if we need to redirect to add new members
        if new_member_count > current_member_count:
            return redirect(url_for('main.lanjutan', success='Data keluarga berhasil diperbarui. Silakan tambahkan anggota baru.'))
        else:
            return redirect(url_for('main.final_page', success='Data keluarga berhasil diperbarui'))

    except Exception as e:
        current_app.logger.error(f"ERROR in edit_family: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return redirect(url_for('main.edit_keluarga', error=f'Error: {str(e)}'))

@bp.route('/api/quick-stats')
@login_required
def api_quick_stats():
    """API endpoint for quick statistics"""
    try:
        stats = get_database_stats()
        
        # Calculate employed/unemployed from employment stats
        total_employed = 0
        total_unemployed = 0
        
        for stat in stats['employment_stats']:
            if hasattr(stat, 'memiliki_pekerjaan'):
                status = stat.memiliki_pekerjaan
                count = stat.jumlah
            else:
                # Direct query result
                status = stat[0] if isinstance(stat, (list, tuple)) else stat['memiliki_pekerjaan']
                count = stat[1] if isinstance(stat, (list, tuple)) else stat['jumlah']
            
            if status == 'Ya':
                total_employed = count
            elif status == 'Tidak':
                total_unemployed = count
        
        return {
            'total_families': stats['total_families'],
            'total_individuals': stats['total_individuals'],
            'total_employed': total_employed,
            'total_unemployed': total_unemployed
        }
        
    except Exception as e:
        current_app.logger.error(f"Error in api_quick_stats: {str(e)}")
        return {
            'total_families': 0,
            'total_individuals': 0,
            'total_employed': 0,
            'total_unemployed': 0
        }
