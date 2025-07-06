import sys
import sqlite3
import csv
from datetime import datetime, date
import requests
import json
import os
import pathlib # For APP_DATA_DIR
import io # For MediaIoBaseUpload

from mindee import Client as MindeeClient, product as mindee_product
from mindee.errors import MindeeClientError, MindeeHttpError

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QComboBox,
    QMessageBox, QHeaderView, QLabel, QFileDialog, QMenu, QTextEdit,
    QSpinBox, QGroupBox, QInputDialog # Added QInputDialog for restore choice
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QAction # Added QAction for menu items

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from fpdf import FPDF

# Google Drive API imports
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials as GoogleCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build as build_google_service
from googleapiclient.errors import HttpError as GoogleHttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


# --- Google Drive Manager ---
# Constants for Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file'] # .file scope for app-specific data
APP_NAME = 'HomeAssetManager'
APP_DATA_SUBDIR = '.home_asset_manager'
TOKEN_FILE = 'token.json'
CLIENT_SECRET_FILE = 'client_secret.json' # User needs to provide this
BACKUP_FILENAME = 'home_assets_backup.db'

def get_app_data_dir():
    """Gets the application data directory path."""
    home = pathlib.Path.home()
    app_data_dir = home / APP_DATA_SUBDIR
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir

class GoogleDriveManager:
    def __init__(self, parent_widget=None):
        self.parent_widget = parent_widget # For showing messages
        self.app_data_path = get_app_data_dir()
        self.token_path = self.app_data_path / TOKEN_FILE
        self.client_secret_path = self.app_data_path / CLIENT_SECRET_FILE
        self.creds = None

    def get_credentials(self):
        if self.creds and self.creds.valid:
            return self.creds
        if self.token_path.exists():
            self.creds = GoogleCredentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(GoogleAuthRequest())
                except Exception as e:
                    QMessageBox.warning(self.parent_widget, "Token Refresh Error", f"Could not refresh token: {e}\nPlease try authorizing again.")
                    self.creds = None # Force re-auth
            else:
                if not self.client_secret_path.exists():
                    QMessageBox.critical(self.parent_widget, "Client Secret Missing",
                                         f"'{CLIENT_SECRET_FILE}' not found in {self.app_data_path}.\n\n"
                                         f"Please download your OAuth 2.0 client secret JSON from Google Cloud Console "
                                         f"(for a 'Desktop app') and place it there. Then try again.")
                    return None
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_path), SCOPES)
                    # Force consent prompt every time for security with local server, or use specific port
                    self.creds = flow.run_local_server(port=0, prompt='consent')
                except Exception as e:
                    QMessageBox.critical(self.parent_widget, "Authentication Error", f"Failed to authenticate with Google: {e}")
                    return None
            # Save the credentials for the next run
            with open(self.token_path, 'w') as token_f:
                token_f.write(self.creds.to_json())
        return self.creds

    def build_service(self):
        creds = self.get_credentials()
        if not creds:
            return None
        try:
            service = build_google_service('drive', 'v3', credentials=creds)
            return service
        except Exception as e:
            QMessageBox.critical(self.parent_widget, "Service Build Error", f"Failed to build Google Drive service: {e}")
            return None

    def backup_database(self, local_db_path='assets.db'):
        service = self.build_service()
        if not service: return False

        # Check if backup file already exists to update it
        file_id = None
        try:
            response = service.files().list(
                q=f"name='{BACKUP_FILENAME}' and trashed=false",
                spaces='drive', fields='files(id, name)').execute()
            if response.get('files'):
                file_id = response.get('files')[0].get('id')
        except GoogleHttpError as e:
            QMessageBox.warning(self.parent_widget, "Drive Error", f"Could not search for existing backup: {e}")
            # Continue to try uploading as a new file if search fails but not critical

        file_metadata = {'name': BACKUP_FILENAME}
        media = MediaFileUpload(local_db_path, mimetype='application/octet-stream', resumable=True)

        try:
            if file_id: # Update existing file
                updated_file = service.files().update(fileId=file_id, media_body=media, fields='id').execute()
                QMessageBox.information(self.parent_widget, "Backup Complete", f"Database backup updated on Google Drive (ID: {updated_file.get('id')}).")
            else: # Create new file
                file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                QMessageBox.information(self.parent_widget, "Backup Complete", f"Database backed up to Google Drive (ID: {file.get('id')}).")
            return True
        except GoogleHttpError as e:
            QMessageBox.critical(self.parent_widget, "Backup Failed", f"An error occurred during backup: {e}")
            return False
        except Exception as e: # Catch other potential errors like file not found for upload
            QMessageBox.critical(self.parent_widget, "Backup Error", f"A local error occurred: {e}")
            return False


    def list_backup_files(self):
        service = self.build_service()
        if not service: return []
        try:
            response = service.files().list(
                q=f"name='{BACKUP_FILENAME}' and trashed=false",
                spaces='drive', fields='files(id, name, modifiedTime)', orderBy='modifiedTime desc').execute()
            return response.get('files', [])
        except GoogleHttpError as e:
            QMessageBox.critical(self.parent_widget, "Drive Error", f"Could not list backup files: {e}")
            return []

    def download_backup(self, file_id, destination_path='assets.db_restored'):
        service = self.build_service()
        if not service: return False
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        try:
            while done is False:
                status, done = downloader.next_chunk()
                # print(F'Download {int(status.progress() * 100)}.') # For console progress
            fh.seek(0)
            with open(destination_path, 'wb') as f:
                f.write(fh.read())
            return True
        except GoogleHttpError as e:
            QMessageBox.critical(self.parent_widget, "Download Failed", f"An error occurred during download: {e}")
            return False

# --- Utility Functions (calculate_acv, get_db_connection - unchanged) ---
# ... (These functions remain the same as in the previous version)
def get_db_connection():
    conn = sqlite3.connect('assets.db')
    conn.row_factory = sqlite3.Row
    return conn

def calculate_acv(rcv, purchase_date_str, useful_life_years, purchase_price_str=None):
    if not all([rcv, purchase_date_str, useful_life_years is not None]): # useful_life_years can be 0
        return None
    if useful_life_years <= 0:
        return rcv

    try:
        purchase_dt = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

    age_days = (date.today() - purchase_dt).days
    if age_days < 0:
        return rcv

    age_years = age_days / 365.25
    annual_depreciation = rcv / useful_life_years
    accumulated_depreciation = annual_depreciation * age_years
    calculated_acv = rcv - accumulated_depreciation
    return max(0, min(calculated_acv, rcv))

# --- Report Dialogs (ReportDialog, LocationReportDialog - unchanged) ---
# ... (These classes remain the same)
class ReportDialog(QDialog):
    def __init__(self, title, headers, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 400)
        layout = QVBoxLayout(self)
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setRowCount(len(data))
        for row_idx, row_data in enumerate(data):
            for col_idx, col_key in enumerate(headers):
                table.setItem(row_idx, col_idx, QTableWidgetItem(str(row_data[col_key.lower().replace(' ', '_')] or "")))
        layout.addWidget(table)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignRight)

class LocationReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assets by Location Report")
        self.setMinimumSize(900, 700)
        layout = QVBoxLayout(self)
        conn = get_db_connection()
        assets = conn.execute("SELECT location, name FROM assets ORDER BY location").fetchall()
        conn.close()
        location_counts = {}
        for asset in assets:
            loc = asset['location'] if asset['location'] else 'Unassigned'
            location_counts[loc] = location_counts.get(loc, 0) + 1

        if location_counts:
            sorted_locations = sorted(location_counts.items(), key=lambda item: item[1], reverse=True)
            labels = [item[0] for item in sorted_locations]
            counts = [item[1] for item in sorted_locations]
            chart_canvas = FigureCanvas(Figure(figsize=(10, 5)))
            ax = chart_canvas.figure.subplots()
            ax.bar(labels, counts)
            ax.set_title('Number of Assets per Location')
            ax.set_ylabel('Asset Count')
            chart_canvas.figure.tight_layout()
            layout.addWidget(chart_canvas)
        else:
            layout.addWidget(QLabel("No assets with location data to display."))

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Location", "Asset Name"])
        table.setRowCount(len(assets))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for idx, asset in enumerate(assets):
            loc = asset['location'] if asset['location'] else 'Unassigned'
            table.setItem(idx, 0, QTableWidgetItem(loc))
            table.setItem(idx, 1, QTableWidgetItem(asset['name']))
        layout.addWidget(table)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignRight)

# --- AssetDialog (unchanged from previous version with insurance features) ---
# ... (This class remains the same)
class AssetDialog(QDialog):
    MINDEE_API_KEY = "YOUR_MINDEE_API_KEY_PLACEHOLDER"
    data_changed_for_acv = Signal()

    def __init__(self, asset_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Asset")
        self.setMinimumWidth(550)
        self.float_validator = QDoubleValidator(0, 9999999.99, 2)
        self.float_validator.setNotation(QDoubleValidator.StandardNotation)
        main_layout = QVBoxLayout(self)
        general_group = QGroupBox("General Information")
        general_layout = QFormLayout(general_group)
        barcode_hbox = QHBoxLayout()
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan or type barcode and press Enter")
        self.barcode_input.returnPressed.connect(self.fetch_product_info_from_barcode)
        barcode_hbox.addWidget(self.barcode_input)
        fetch_barcode_button = QPushButton("Fetch Barcode Info")
        fetch_barcode_button.clicked.connect(self.fetch_product_info_from_barcode)
        barcode_hbox.addWidget(fetch_barcode_button)
        general_layout.addRow("Barcode:", barcode_hbox)
        scan_receipt_button = QPushButton("Scan Receipt Image")
        scan_receipt_button.clicked.connect(self.scan_receipt_image)
        general_layout.addRow(scan_receipt_button)
        self.asset_type = QComboBox()
        self.asset_type.addItems(["Hardware", "Software", "Furniture", "Appliance", "Electronics", "Jewelry", "Art", "Collectible", "General Item", "Other"])
        self.name = QLineEdit()
        self.quantity = QSpinBox()
        self.quantity.setMinimum(1); self.quantity.setMaximum(99999)
        self.manufacturer = QLineEdit()
        self.model = QLineEdit()
        self.description = QTextEdit(); self.description.setFixedHeight(60)
        self.serial_or_license_key = QLineEdit()
        self.location = QLineEdit()
        self.vendor = QLineEdit()
        self.bought_at = QLineEdit()
        general_layout.addRow("Asset Type:", self.asset_type)
        general_layout.addRow("Name:", self.name)
        general_layout.addRow("Quantity:", self.quantity)
        general_layout.addRow("Manufacturer:", self.manufacturer)
        general_layout.addRow("Model:", self.model)
        general_layout.addRow("Description:", self.description)
        general_layout.addRow("Serial/License Key:", self.serial_or_license_key)
        general_layout.addRow("Location:", self.location)
        general_layout.addRow("Vendor/Supplier:", self.vendor)
        general_layout.addRow("Bought At (Store):", self.bought_at)
        main_layout.addWidget(general_group)
        purchase_group = QGroupBox("Purchase & Warranty Details")
        purchase_layout = QFormLayout(purchase_group)
        self.purchase_date = QLineEdit(); self.purchase_date.setPlaceholderText("YYYY-MM-DD")
        self.purchase_price = QLineEdit(); self.purchase_price.setPlaceholderText("e.g., 299.99 (single)"); self.purchase_price.setValidator(self.float_validator)
        self.warranty_or_sub_start = QLineEdit(); self.warranty_or_sub_start.setPlaceholderText("YYYY-MM-DD")
        self.warranty_or_sub_end = QLineEdit(); self.warranty_or_sub_end.setPlaceholderText("YYYY-MM-DD")
        purchase_layout.addRow("Purchase Date:", self.purchase_date)
        purchase_layout.addRow("Purchase Price (single):", self.purchase_price)
        purchase_layout.addRow("Warranty/Sub Start:", self.warranty_or_sub_start)
        purchase_layout.addRow("Warranty/Sub End:", self.warranty_or_sub_end)
        main_layout.addWidget(purchase_group)
        insurance_group = QGroupBox("Insurance Valuation")
        insurance_layout = QFormLayout(insurance_group)
        self.rcv_input = QLineEdit(); self.rcv_input.setPlaceholderText("e.g., 350.00"); self.rcv_input.setValidator(self.float_validator)
        self.useful_life_years_input = QSpinBox(); self.useful_life_years_input.setMinimum(0); self.useful_life_years_input.setMaximum(100); self.useful_life_years_input.setSuffix(" years")
        self.acv_override_input = QLineEdit(); self.acv_override_input.setPlaceholderText("Optional (e.g., 150.00)"); self.acv_override_input.setValidator(self.float_validator)
        self.calculated_acv_display = QLineEdit(); self.calculated_acv_display.setReadOnly(True); self.calculated_acv_display.setStyleSheet("background-color: #f0f0f0;")
        insurance_layout.addRow("Replacement Cost Value (RCV):", self.rcv_input)
        insurance_layout.addRow("Useful Life:", self.useful_life_years_input)
        insurance_layout.addRow("Calculated ACV:", self.calculated_acv_display)
        insurance_layout.addRow("ACV Override (Optional):", self.acv_override_input)
        main_layout.addWidget(insurance_group)
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self.notes = QTextEdit(); self.notes.setFixedHeight(80)
        notes_layout.addWidget(self.notes)
        main_layout.addWidget(notes_group)
        self.rcv_input.textChanged.connect(self.data_changed_for_acv.emit)
        self.purchase_date.textChanged.connect(self.data_changed_for_acv.emit)
        self.useful_life_years_input.valueChanged.connect(self.data_changed_for_acv.emit)
        self.acv_override_input.textChanged.connect(self.data_changed_for_acv.emit)
        self.purchase_price.textChanged.connect(self.sync_purchase_price_to_rcv_if_empty)
        self.data_changed_for_acv.connect(self.update_calculated_acv_display)
        if asset_data: self.populate_fields(asset_data)
        else: self.quantity.setValue(1); self.useful_life_years_input.setValue(0); self.update_calculated_acv_display()
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept_dialog)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)
        self.setLayout(main_layout)
        if asset_data: self.update_calculated_acv_display()

    def sync_purchase_price_to_rcv_if_empty(self):
        if not self.rcv_input.text() and self.purchase_price.text(): self.rcv_input.setText(self.purchase_price.text())

    def update_calculated_acv_display(self):
        override_val_str = self.acv_override_input.text().strip()
        if override_val_str:
            try: self.calculated_acv_display.setText(f"{float(override_val_str):.2f} (Override)"); return
            except ValueError: pass
        try: rcv = float(self.rcv_input.text()) if self.rcv_input.text() else 0.0
        except ValueError: rcv = 0.0
        acv = calculate_acv(rcv, self.purchase_date.text(), self.useful_life_years_input.value())
        self.calculated_acv_display.setText(f"{acv:.2f}" if acv is not None else "N/A (Info missing)")

    def populate_fields(self, d): # d for asset_data_dict
        self.asset_type.setCurrentText(d.get('asset_type', "General Item")); self.barcode_input.setText(d.get('barcode', ''))
        self.name.setText(d.get('name', '')); self.quantity.setValue(d.get('quantity', 1))
        self.manufacturer.setText(d.get('manufacturer', '')); self.model.setText(d.get('model', ''))
        self.description.setPlainText(d.get('description', '')); self.serial_or_license_key.setText(d.get('serial_or_license_key', ''))
        self.location.setText(d.get('location', '')); self.vendor.setText(d.get('vendor', '')); self.bought_at.setText(d.get('bought_at', ''))
        self.notes.setPlainText(d.get('notes', '')); self.purchase_date.setText(d.get('purchase_date', ''))
        self.purchase_price.setText(str(d.get('purchase_price', '')) if d.get('purchase_price') is not None else '')
        self.warranty_or_sub_start.setText(d.get('warranty_or_sub_start', '')); self.warranty_or_sub_end.setText(d.get('warranty_or_sub_end', ''))
        self.rcv_input.setText(str(d.get('rcv', '')) if d.get('rcv') is not None else '')
        self.useful_life_years_input.setValue(d.get('useful_life_years', 0))
        self.acv_override_input.setText(str(d.get('acv_override', '')) if d.get('acv_override') is not None else '')
        # self.update_calculated_acv_display() # Called by constructor after populate if asset_data

    def fetch_product_info_from_barcode(self):
        barcode = self.barcode_input.text().strip()
        if not barcode: QMessageBox.warning(self, "Barcode Empty", "Please enter a barcode."); return
        url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}"
        try:
            response = requests.get(url, timeout=10); response.raise_for_status(); data = response.json()
            if data.get('code') == "OK" and data.get('items'):
                item_info = data['items'][0]
                if not self.name.text(): self.name.setText(item_info.get('title', ''))
                if not self.manufacturer.text(): self.manufacturer.setText(item_info.get('brand', ''))
                if not self.model.text(): self.model.setText(item_info.get('model', ''))
                if not self.description.toPlainText(): self.description.setPlainText(item_info.get('description', ''))
                QMessageBox.information(self, "Success", "Product info fetched. Fields updated if previously empty.")
            elif data.get('code') == "INVALID_UPC" or not data.get('items'): QMessageBox.warning(self, "Not Found", f"No product information found for barcode: {barcode}")
            else: QMessageBox.warning(self, "API Error", f"Could not retrieve product information. API response: {data.get('message', 'Unknown error')}")
        except requests.exceptions.RequestException as e: QMessageBox.critical(self, "Network Error", f"Barcode lookup connection error: {e}")
        except json.JSONDecodeError: QMessageBox.critical(self, "API Error", "Invalid response from barcode lookup service.")

    def scan_receipt_image(self):
        if self.MINDEE_API_KEY == "YOUR_MINDEE_API_KEY_PLACEHOLDER": QMessageBox.critical(self, "API Key Missing", "Mindee API key missing."); return
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Receipt Image", "", "Image Files (*.png *.jpg *.jpeg *.pdf)");
        if not filepath: return
        try:
            mindee_client = MindeeClient(api_key=self.MINDEE_API_KEY); input_doc = mindee_client.source_from_path(filepath)
            result = mindee_client.parse(mindee_product.ReceiptV5, input_doc)
            if result.document and result.document.inference and result.document.inference.prediction:
                pred = result.document.inference.prediction
                if pred.supplier_name and pred.supplier_name.value: self.vendor.setText(pred.supplier_name.value)
                if pred.date and pred.date.value: self.purchase_date.setText(pred.date.value)
                if pred.total_amount and pred.total_amount.value is not None:
                    price_str = str(pred.total_amount.value)
                    self.purchase_price.setText(price_str)
                    if not self.rcv_input.text(): self.rcv_input.setText(price_str)
                items_text = [f"{li.description or 'N/A'} (Qty: {li.quantity or ''}, Total: {li.total_amount or ''})" for li in pred.line_items if li.description]
                if items_text:
                    if not self.name.text() and pred.line_items[0].description: self.name.setText(pred.line_items[0].description)
                    desc = self.description.toPlainText(); self.description.setPlainText(desc + "\n\nReceipt Items:\n" + "\n".join(items_text) if desc else "Receipt Items:\n" + "\n".join(items_text))
                QMessageBox.information(self, "Receipt Scanned", "Receipt data extracted.")
            else: QMessageBox.warning(self, "Scan Failed", "Could not extract data from receipt.")
        except (MindeeClientError, MindeeHttpError) as e: QMessageBox.critical(self, "Mindee API Error", f"Mindee error: {e}")
        except Exception as e: QMessageBox.critical(self, "Processing Error", f"Unexpected error: {e}")

    def get_data(self):
        def to_float_or_none(val_str):
            try: return float(val_str) if val_str.strip() else None
            except ValueError: return None
        return {
            "asset_type": self.asset_type.currentText(), "barcode": self.barcode_input.text().strip(),
            "name": self.name.text().strip(), "quantity": self.quantity.value(),
            "manufacturer": self.manufacturer.text().strip(), "model": self.model.text().strip(),
            "description": self.description.toPlainText().strip(), "serial_or_license_key": self.serial_or_license_key.text().strip(),
            "purchase_date": self.purchase_date.text().strip(), "purchase_price": to_float_or_none(self.purchase_price.text()),
            "warranty_or_sub_start": self.warranty_or_sub_start.text().strip(), "warranty_or_sub_end": self.warranty_or_sub_end.text().strip(),
            "location": self.location.text().strip(), "vendor": self.vendor.text().strip(), "bought_at": self.bought_at.text().strip(),
            "notes": self.notes.toPlainText().strip(), "rcv": to_float_or_none(self.rcv_input.text()),
            "useful_life_years": self.useful_life_years_input.value() if self.useful_life_years_input.value() > 0 else None,
            "acv_override": to_float_or_none(self.acv_override_input.text())
        }

    def accept_dialog(self):
        date_fields = {"Purchase Date": self.purchase_date, "Warranty Start": self.warranty_or_sub_start, "Warranty End": self.warranty_or_sub_end}
        for name, field in date_fields.items():
            if field.text().strip():
                try: datetime.strptime(field.text().strip(), '%Y-%m-%d')
                except ValueError: QMessageBox.warning(self, "Invalid Date", f"Invalid date for {name}. Use YYYY-MM-DD or empty."); return
        self.accept()


# --- Main Application Window (MODIFIED for Google Drive) ---
class AssetTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Home Asset Management Pro")
        self.setGeometry(100, 100, 1600, 800)
        self.gdrive_manager = GoogleDriveManager(parent_widget=self) # Initialize manager

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self._create_menus() # Create menus

        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.assets_tab = QWidget()
        self.tabs.addTab(self.assets_tab, "All Assets")
        self.setup_assets_tab_ui(self.assets_tab)
        self.load_assets()

    def _create_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        backup_action = QAction("&Backup to Google Drive", self)
        backup_action.triggered.connect(self.backup_to_drive)
        file_menu.addAction(backup_action)

        restore_action = QAction("&Restore from Google Drive", self)
        restore_action.triggered.connect(self.restore_from_drive)
        file_menu.addAction(restore_action)

        file_menu.addSeparator()
        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Reports menu will be part of setup_assets_tab_ui for now or can be moved here

    def backup_to_drive(self):
        # Ensure database is closed if SQLite is sensitive to concurrent access during copy
        # For simplicity, we assume direct file copy is okay for SQLite if app is not actively writing.
        # A more robust solution might involve closing the DB connection, copying, then reopening.

        # Check if client_secret.json exists, guide user if not
        if not self.gdrive_manager.client_secret_path.exists():
             QMessageBox.information(self, "Setup Required for Google Drive",
                                  f"To use Google Drive backup, please place your '{CLIENT_SECRET_FILE}' "
                                  f"in the following directory: {self.gdrive_manager.app_data_path}\n\n"
                                  "You can obtain this file from the Google Cloud Console for your OAuth 2.0 Desktop Client ID.")
             return

        # Check credentials (this will trigger auth flow if needed)
        if not self.gdrive_manager.get_credentials():
            QMessageBox.warning(self, "Google Drive Auth Failed", "Could not authenticate with Google Drive. Please try again or check configuration.")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        db_file_path = 'assets.db'
        if not os.path.exists(db_file_path):
            QMessageBox.critical(self, "Error", "Local database file 'assets.db' not found.")
            QApplication.restoreOverrideCursor()
            return

        success = self.gdrive_manager.backup_database(db_file_path)
        QApplication.restoreOverrideCursor()
        # Backup_database method in GoogleDriveManager already shows success/failure message.

    def restore_from_drive(self):
        if not self.gdrive_manager.client_secret_path.exists():
             QMessageBox.information(self, "Setup Required for Google Drive",
                                  f"To use Google Drive restore, please place your '{CLIENT_SECRET_FILE}' "
                                  f"in the following directory: {self.gdrive_manager.app_data_path}")
             return
        if not self.gdrive_manager.get_credentials():
            QMessageBox.warning(self, "Google Drive Auth Failed", "Could not authenticate with Google Drive.")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        backups = self.gdrive_manager.list_backup_files()
        QApplication.restoreOverrideCursor()

        if not backups:
            QMessageBox.information(self, "No Backups Found", f"No backup file named '{BACKUP_FILENAME}' found on your Google Drive.")
            return

        # For MVP, let's assume only one relevant backup file or use the latest.
        # A more advanced version would let the user choose from a list if multiple exist.
        # For now, just take the first one (which should be the latest due to orderBy='modifiedTime desc')
        backup_to_restore = backups[0]
        file_id = backup_to_restore['id']
        file_name = backup_to_restore['name']
        modified_time = backup_to_restore.get('modifiedTime', 'Unknown time')

        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Restore database from Google Drive?\n\n"
                                     f"File: {file_name}\n"
                                     f"Last Modified (UTC): {modified_time}\n\n"
                                     "This will overwrite your current local database. It's recommended to backup your current data first if needed.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        # Perform the download
        QApplication.setOverrideCursor(Qt.WaitCursor)
        restored_db_path = 'assets.db' # Overwrite current DB
        # It's safer to download to a temporary name first, then replace.
        temp_restored_db_path = 'assets.db_restored_temp'

        success = self.gdrive_manager.download_backup(file_id, temp_restored_db_path)
        QApplication.restoreOverrideCursor()

        if success:
            # Close current connection if any, then replace file
            # For simplicity, we'll just replace. The app needs a robust way to handle DB connections during this.
            # Ideally, close DB, replace file, then inform user to reload/restart.
            try:
                # Ensure any existing DB connection by a get_db_connection() is closed.
                # This is tricky without a central DB manager. For now, assume OS can handle file replace.
                # If app holds assets.db open, this might fail on some OS.
                if os.path.exists(restored_db_path):
                    os.remove(restored_db_path)
                os.rename(temp_restored_db_path, restored_db_path)
                QMessageBox.information(self, "Restore Complete",
                                        "Database restored successfully from Google Drive.\n"
                                        "Please reload the assets (or restart the application if issues persist).")
                self.load_assets() # Reload data
            except Exception as e:
                QMessageBox.critical(self, "File Replace Error", f"Could not replace local database: {e}")
                if os.path.exists(temp_restored_db_path): os.remove(temp_restored_db_path) # Clean up
        else:
            if os.path.exists(temp_restored_db_path): os.remove(temp_restored_db_path) # Clean up failed download


    def setup_assets_tab_ui(self, tab):
        # ... (Column definitions and other UI setup remains the same)
        layout = QVBoxLayout(tab)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to search across all fields...")
        filter_layout.addWidget(self.search_input)
        layout.addLayout(filter_layout)

        self.assets_table = QTableWidget()
        self.assets_table.setColumnCount(19)
        self.assets_table.setHorizontalHeaderLabels([
            "ID", "Name", "Qty", "Asset Type", "Mfg", "Model",
            "Serial/Lic", "Purch. Date", "Purch. Price", "RCV", "ACV", "Useful Life (Yrs)",
            "Warr. Start", "Warr. End", "Location", "Vendor",
            "Barcode", "Description", "Notes"
        ])
        self.assets_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.assets_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.assets_table.setSelectionMode(QTableWidget.SingleSelection)
        self.assets_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.assets_table.verticalHeader().setVisible(False)
        self.assets_table.setAlternatingRowColors(True)
        layout.addWidget(self.assets_table)

        button_layout = QHBoxLayout()
        add_button = QPushButton("Add Asset"); edit_button = QPushButton("Edit Selected"); delete_button = QPushButton("Delete Selected")
        export_csv_button = QPushButton("Export CSV")

        # Reports button setup now part of main UI setup, not _create_menus
        self.reports_button = QPushButton("Reports") # Made it instance member
        reports_menu = QMenu(self)
        reports_menu.addAction("Expired Warranty Report", self.show_expired_warranty_report)
        reports_menu.addAction("Assets with No Location", self.show_no_location_report)
        reports_menu.addAction("Assets by Location Chart", self.show_location_report)
        reports_menu.addAction("Insurance Detail Report (PDF)", self.show_insurance_report_pdf)
        self.reports_button.setMenu(reports_menu)

        button_layout.addWidget(add_button); button_layout.addWidget(edit_button); button_layout.addWidget(delete_button)
        button_layout.addStretch(); button_layout.addWidget(self.reports_button); button_layout.addWidget(export_csv_button)
        layout.addLayout(button_layout)

        add_button.clicked.connect(self.add_asset)
        edit_button.clicked.connect(self.edit_asset)
        delete_button.clicked.connect(self.delete_asset)
        export_csv_button.clicked.connect(self.export_to_csv_enhanced)
        self.search_input.textChanged.connect(self.filter_assets)
        self.assets_table.doubleClicked.connect(self.edit_asset)


    def show_insurance_report_pdf(self):
        # ... (remains the same)
        path, _ = QFileDialog.getSaveFileName(self, "Save Insurance PDF Report", "Insurance_Report.pdf", "PDF Files (*.pdf)")
        if not path: return
        conn = get_db_connection(); assets = conn.execute("SELECT * FROM assets ORDER BY name").fetchall(); conn.close()
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Home Asset Insurance Report", 0, 1, "C"); pdf.ln(5)
        pdf.set_font("Arial", "B", 8)
        col_widths = {"Name": 40, "Purch. Date": 20, "Purch. Price": 20, "RCV": 15, "Useful Life": 15, "ACV": 15, "Location": 30, "Description": 35}
        header_keys = ["Name", "Purch. Date", "Purch. Price", "RCV", "Useful Life", "ACV", "Location", "Description"]
        for hk in header_keys: pdf.cell(col_widths.get(hk, 20), 7, hk, 1, 0, "C")
        pdf.ln()
        pdf.set_font("Arial", "", 7)
        for asset in assets:
            acv_display = "N/A"
            if asset['acv_override'] is not None: acv_display = f"{asset['acv_override']:.2f} (Override)"
            else:
                acv_val = calculate_acv(asset['rcv'], asset['purchase_date'], asset['useful_life_years'])
                if acv_val is not None: acv_display = f"{acv_val:.2f}"
            desc_text = (asset['description'] or "")[:100] + ('...' if len(asset['description'] or "") > 100 else '')
            pdf.cell(col_widths["Name"], 6, str(asset['name'] or ""), 1)
            pdf.cell(col_widths["Purch. Date"], 6, str(asset['purchase_date'] or ""), 1)
            pdf.cell(col_widths["Purch. Price"], 6, str(asset['purchase_price'] or ""), 1)
            pdf.cell(col_widths["RCV"], 6, str(asset['rcv'] or ""), 1)
            pdf.cell(col_widths["Useful Life"], 6, str(asset['useful_life_years'] or ""), 1)
            pdf.cell(col_widths["ACV"], 6, acv_display, 1)
            pdf.cell(col_widths["Location"], 6, str(asset['location'] or ""), 1)
            pdf.multi_cell(col_widths["Description"], 6, desc_text, 1)
        try: pdf.output(path, "F"); QMessageBox.information(self, "Success", f"Insurance PDF report saved to {path}")
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to save PDF report: {e}")

    def show_expired_warranty_report(self):
        # ... (remains the same)
        conn = get_db_connection(); all_assets = conn.execute("SELECT * FROM assets WHERE warranty_or_sub_end IS NOT NULL AND warranty_or_sub_end != ''").fetchall(); conn.close()
        expired_assets_data = []
        today = datetime.now().date()
        for asset in all_assets:
            try:
                end_date = datetime.strptime(asset['warranty_or_sub_end'], '%Y-%m-%d').date()
                if end_date < today: expired_assets_data.append(asset)
            except (ValueError, TypeError): continue
        headers = ["Name", "Asset Type", "Warranty Or Sub End", "Location"]
        dialog = ReportDialog("Expired Warranty/Subscription Report", headers, expired_assets_data, self); dialog.exec()

    def show_no_location_report(self):
        # ... (remains the same)
        conn = get_db_connection(); assets_no_location = conn.execute("SELECT * FROM assets WHERE location IS NULL OR location = ''").fetchall(); conn.close()
        headers = ["Name", "Asset Type", "Vendor", "Purchase Date"]
        dialog = ReportDialog("Assets with No Location", headers, assets_no_location, self); dialog.exec()

    def show_location_report(self):
        # ... (remains the same)
        dialog = LocationReportDialog(self); dialog.exec()

    def filter_assets(self):
        # ... (remains the same)
        search_text = self.search_input.text().lower()
        for row_num in range(self.assets_table.rowCount()):
            match = False
            for col_num in range(self.assets_table.columnCount()):
                item = self.assets_table.item(row_num, col_num)
                if item and search_text in item.text().lower(): match = True; break
            self.assets_table.setRowHidden(row_num, not match)

    def export_to_csv_enhanced(self):
        # ... (remains the same, ensure it matches table headers if using table data)
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "Assets_Export_Detailed.csv", "CSV Files (*.csv)")
        if not path: return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                headers = [self.assets_table.horizontalHeaderItem(i).text() for i in range(self.assets_table.columnCount())]
                writer.writerow(headers)
                conn = get_db_connection(); db_assets = conn.execute("SELECT * FROM assets ORDER BY name").fetchall(); conn.close()
                for asset in db_assets:
                    acv_display = "N/A"
                    if asset['acv_override'] is not None: acv_display = f"{asset['acv_override']:.2f} (Override)"
                    else:
                        acv_val = calculate_acv(asset['rcv'], asset['purchase_date'], asset['useful_life_years'])
                        if acv_val is not None: acv_display = f"{acv_val:.2f}"
                    # This mapping needs to exactly match the table header order
                    row_data = [
                        str(asset['id'] or ''), str(asset['name'] or ''), str(asset['quantity'] or '1'), str(asset['asset_type'] or ''),
                        str(asset['manufacturer'] or ''), str(asset['model'] or ''), str(asset['serial_or_license_key'] or ''),
                        str(asset['purchase_date'] or ''), str(asset['purchase_price'] or ''),
                        str(asset['rcv'] or ''), acv_display, str(asset['useful_life_years'] or ''),
                        str(asset['warranty_or_sub_start'] or ''), str(asset['warranty_or_sub_end'] or ''),
                        str(asset['location'] or ''), str(asset['vendor'] or ''),
                        str(asset['barcode'] or ''), str(asset['description'] or ''), str(asset['notes'] or '')
                    ]
                    writer.writerow(row_data)
            QMessageBox.information(self, "Success", "Data exported successfully to CSV!")
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to export data to CSV: {e}")


    def load_assets(self):
        # ... (remains the same, ensure indices match new table structure)
        self.assets_table.setRowCount(0)
        conn = get_db_connection(); db_assets = conn.execute("SELECT * FROM assets ORDER BY name").fetchall(); conn.close()
        for asset in db_assets:
            row_position = self.assets_table.rowCount(); self.assets_table.insertRow(row_position)
            def get_str(value, is_float=False):
                if value is None: return ""
                if is_float: return f"{value:.2f}" if isinstance(value, (float, int)) else str(value)
                return str(value)
            acv_display_val = "N/A"
            if asset['acv_override'] is not None: acv_display_val = f"{asset['acv_override']:.2f} (Override)"
            else:
                acv = calculate_acv(asset['rcv'], asset['purchase_date'], asset['useful_life_years'])
                if acv is not None: acv_display_val = f"{acv:.2f}"
            self.assets_table.setItem(row_position, 0, QTableWidgetItem(get_str(asset['id'])))
            self.assets_table.setItem(row_position, 1, QTableWidgetItem(get_str(asset['name'])))
            self.assets_table.setItem(row_position, 2, QTableWidgetItem(get_str(asset['quantity'])))
            self.assets_table.setItem(row_position, 3, QTableWidgetItem(get_str(asset['asset_type'])))
            self.assets_table.setItem(row_position, 4, QTableWidgetItem(get_str(asset['manufacturer'])))
            self.assets_table.setItem(row_position, 5, QTableWidgetItem(get_str(asset['model'])))
            self.assets_table.setItem(row_position, 6, QTableWidgetItem(get_str(asset['serial_or_license_key'])))
            self.assets_table.setItem(row_position, 7, QTableWidgetItem(get_str(asset['purchase_date'])))
            self.assets_table.setItem(row_position, 8, QTableWidgetItem(get_str(asset['purchase_price'], True)))
            self.assets_table.setItem(row_position, 9, QTableWidgetItem(get_str(asset['rcv'], True)))
            self.assets_table.setItem(row_position, 10, QTableWidgetItem(acv_display_val))
            self.assets_table.setItem(row_position, 11, QTableWidgetItem(get_str(asset['useful_life_years'])))
            self.assets_table.setItem(row_position, 12, QTableWidgetItem(get_str(asset['warranty_or_sub_start'])))
            self.assets_table.setItem(row_position, 13, QTableWidgetItem(get_str(asset['warranty_or_sub_end'])))
            self.assets_table.setItem(row_position, 14, QTableWidgetItem(get_str(asset['location'])))
            self.assets_table.setItem(row_position, 15, QTableWidgetItem(get_str(asset['vendor'])))
            self.assets_table.setItem(row_position, 16, QTableWidgetItem(get_str(asset['barcode'])))
            self.assets_table.setItem(row_position, 17, QTableWidgetItem(get_str(asset['description'])))
            self.assets_table.setItem(row_position, 18, QTableWidgetItem(get_str(asset['notes'])))
        self.assets_table.resizeColumnsToContents()

    def add_asset(self):
        # ... (remains the same, ensure SQL matches DB)
        dialog = AssetDialog(parent=self)
        if dialog.exec():
            data = dialog.get_data()
            conn = get_db_connection()
            try:
                conn.execute("""
                    INSERT INTO assets (asset_type, name, quantity, manufacturer, model, description, serial_or_license_key,
                                      purchase_date, purchase_price, warranty_or_sub_start, warranty_or_sub_end,
                                      location, vendor, bought_at, barcode, notes,
                                      rcv, useful_life_years, acv_override)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (data['asset_type'], data['name'], data['quantity'], data['manufacturer'], data['model'], data['description'],
                      data['serial_or_license_key'], data['purchase_date'], data['purchase_price'],
                      data['warranty_or_sub_start'], data['warranty_or_sub_end'], data['location'],
                      data['vendor'], data['bought_at'], data['barcode'], data['notes'],
                      data['rcv'], data['useful_life_years'], data['acv_override']))
                conn.commit()
            except sqlite3.Error as e: QMessageBox.critical(self, "Database Error", f"Could not add asset: {e}")
            finally: conn.close()
            self.load_assets()

    def edit_asset(self):
        # ... (remains the same, ensure SQL matches DB)
        selected_row = self.assets_table.currentRow()
        if selected_row < 0:
            if self.sender() == self.assets_table and not self.assets_table.item(selected_row,0) : return
            QMessageBox.warning(self, "Warning", "Please select an asset to edit.")
            return
        asset_id_item = self.assets_table.item(selected_row, 0);
        if not asset_id_item: return
        asset_id = int(asset_id_item.text())
        conn = get_db_connection(); asset_data_row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone(); conn.close()
        if not asset_data_row: QMessageBox.critical(self, "Error", "Could not find asset in DB."); return
        dialog = AssetDialog(asset_data=dict(asset_data_row), parent=self)
        if dialog.exec():
            new_data = dialog.get_data()
            conn = get_db_connection()
            try:
                conn.execute("""
                    UPDATE assets SET
                        asset_type = ?, name = ?, quantity = ?, manufacturer = ?, model = ?, description = ?,
                        serial_or_license_key = ?, purchase_date = ?, purchase_price = ?,
                        warranty_or_sub_start = ?, warranty_or_sub_end = ?, location = ?,
                        vendor = ?, bought_at = ?, barcode = ?, notes = ?,
                        rcv = ?, useful_life_years = ?, acv_override = ?
                    WHERE id = ?
                """, (new_data['asset_type'], new_data['name'], new_data['quantity'], new_data['manufacturer'], new_data['model'], new_data['description'],
                      new_data['serial_or_license_key'], new_data['purchase_date'], new_data['purchase_price'],
                      new_data['warranty_or_sub_start'], new_data['warranty_or_sub_end'], new_data['location'],
                      new_data['vendor'], new_data['bought_at'], new_data['barcode'], new_data['notes'],
                      new_data['rcv'], new_data['useful_life_years'], new_data['acv_override'], asset_id))
                conn.commit()
            except sqlite3.Error as e: QMessageBox.critical(self, "Database Error", f"Could not update asset: {e}")
            finally: conn.close()
            self.load_assets()

    def delete_asset(self):
        # ... (remains the same)
        selected_row = self.assets_table.currentRow()
        if selected_row < 0: QMessageBox.warning(self, "Warning", "Please select an asset to delete."); return
        asset_id = int(self.assets_table.item(selected_row, 0).text())
        asset_name = self.assets_table.item(selected_row, 1).text()
        reply = QMessageBox.question(self, 'Delete Asset', f"Delete '{asset_name}' (ID: {asset_id})?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = get_db_connection()
            try: conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,)); conn.commit()
            except sqlite3.Error as e: QMessageBox.critical(self, "Database Error", f"Could not delete asset: {e}")
            finally: conn.close()
            self.load_assets()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Make sure AppData dir exists for token/client_secret
    get_app_data_dir()
    window = AssetTracker()
    window.show()
    sys.exit(app.exec())
