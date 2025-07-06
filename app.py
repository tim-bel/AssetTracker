import sys
import sqlite3
import csv
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QComboBox,
    QMessageBox, QHeaderView, QLabel, QFileDialog, QMenu
)
from PySide6.QtCore import Qt

# --- Matplotlib Imports for Charting ---
# This library needs to be installed: pip install matplotlib
import matplotlib
matplotlib.use('Qt5Agg') # Specify the backend to use with PySide
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect('assets.db')
    conn.row_factory = sqlite3.Row 
    return conn

# --- Generic Report Dialog ---
class ReportDialog(QDialog):
    """A dialog to display simple, table-based reports."""
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
                # sqlite3.Row can be accessed by index or key, we use key.
                # The 'or ""' handles cases where the data might be None.
                table.setItem(row_idx, col_idx, QTableWidgetItem(str(row_data[col_key.lower().replace(' ', '_')] or "")))

        layout.addWidget(table)
        
        # Add a close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignRight)

# --- Location Report Dialog with Chart ---
class LocationReportDialog(QDialog):
    """A specialized dialog to show assets grouped by location with a bar chart."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assets by Location Report")
        self.setMinimumSize(900, 700)

        layout = QVBoxLayout(self)

        # 1. Get and process data
        conn = get_db_connection()
        assets = conn.execute("SELECT location, name FROM assets ORDER BY location").fetchall()
        conn.close()

        location_counts = {}
        for asset in assets:
            # Treat empty or None locations as 'Unassigned'
            loc = asset['location'] if asset['location'] else 'Unassigned'
            location_counts[loc] = location_counts.get(loc, 0) + 1
        
        # 2. Create the Matplotlib chart
        # Sort locations by count for a nicer chart
        sorted_locations = sorted(location_counts.items(), key=lambda item: item[1], reverse=True)
        labels = [item[0] for item in sorted_locations]
        counts = [item[1] for item in sorted_locations]

        chart_canvas = FigureCanvas(Figure(figsize=(10, 5)))
        ax = chart_canvas.figure.subplots()
        ax.bar(labels, counts)
        ax.set_title('Number of Assets per Location')
        ax.set_ylabel('Asset Count')
        chart_canvas.figure.tight_layout() # Adjust layout to prevent labels overlapping
        
        layout.addWidget(chart_canvas)

        # 3. Create the detailed table
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

# --- Add/Edit Asset Dialog (Unchanged) ---
class AssetDialog(QDialog):
    def __init__(self, asset_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Asset")
        self.setMinimumWidth(400)
        self.asset_type = QComboBox()
        self.asset_type.addItems(["Hardware", "Software"])
        self.name = QLineEdit()
        self.serial_or_license_key = QLineEdit()
        self.purchase_date = QLineEdit()
        self.warranty_or_sub_start = QLineEdit()
        self.warranty_or_sub_end = QLineEdit()
        self.location = QLineEdit()
        self.vendor = QLineEdit()
        self.bought_at = QLineEdit()
        self.notes = QLineEdit()
        if asset_data:
            self.asset_type.setCurrentText(asset_data['asset_type'])
            self.name.setText(asset_data['name'])
            self.serial_or_license_key.setText(asset_data['serial_or_license_key'] or '')
            self.purchase_date.setText(asset_data['purchase_date'] or '')
            self.warranty_or_sub_start.setText(asset_data['warranty_or_sub_start'] or '')
            self.warranty_or_sub_end.setText(asset_data['warranty_or_sub_end'] or '')
            self.location.setText(asset_data['location'] or '')
            self.vendor.setText(asset_data['vendor'] or '')
            self.bought_at.setText(asset_data['bought_at'] or '')
            self.notes.setText(asset_data['notes'] or '')
        form_layout = QFormLayout()
        form_layout.addRow("Asset Type:", self.asset_type)
        form_layout.addRow("Name:", self.name)
        form_layout.addRow("Serial/License Key:", self.serial_or_license_key)
        form_layout.addRow("Purchase Date (YYYY-MM-DD):", self.purchase_date)
        form_layout.addRow("Warranty/Sub Start (YYYY-MM-DD):", self.warranty_or_sub_start)
        form_layout.addRow("Warranty/Sub End (YYYY-MM-DD):", self.warranty_or_sub_end)
        form_layout.addRow("Location:", self.location)
        form_layout.addRow("Vendor:", self.vendor)
        form_layout.addRow("Bought At:", self.bought_at)
        form_layout.addRow("Notes:", self.notes)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)
        self.setLayout(main_layout)
    def get_data(self):
        return {"asset_type": self.asset_type.currentText(), "name": self.name.text(), "serial_or_license_key": self.serial_or_license_key.text(), "purchase_date": self.purchase_date.text(), "warranty_or_sub_start": self.warranty_or_sub_start.text(), "warranty_or_sub_end": self.warranty_or_sub_end.text(), "location": self.location.text(), "vendor": self.vendor.text(), "bought_at": self.bought_at.text(), "notes": self.notes.text()}

# --- Main Application Window ---
class AssetTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Business Asset Tracker")
        self.setGeometry(100, 100, 1200, 700)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.hardware_tab = QWidget()
        self.software_tab = QWidget()
        self.tabs.addTab(self.hardware_tab, "Hardware Assets")
        self.tabs.addTab(self.software_tab, "Software Assets")
        self.setup_tab_ui(self.hardware_tab, "Hardware")
        self.setup_tab_ui(self.software_tab, "Software")
        self.load_assets()

    def setup_tab_ui(self, tab, asset_type):
        layout = QVBoxLayout(tab)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        search_input = QLineEdit()
        search_input.setPlaceholderText("Type to search...")
        filter_layout.addWidget(search_input)
        layout.addLayout(filter_layout)
        table = QTableWidget()
        table.setColumnCount(10)
        table.setHorizontalHeaderLabels(["ID", "Name", "Serial/License", "Purchase Date", "Warranty/Sub Start", "Warranty/Sub End", "Location", "Vendor", "Bought At", "Notes"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        if asset_type == "Hardware":
            self.hardware_table = table
            self.hardware_search = search_input
        else:
            self.software_table = table
            self.software_search = search_input
        layout.addWidget(table)
        button_layout = QHBoxLayout()
        add_button = QPushButton(f"Add {asset_type}")
        edit_button = QPushButton(f"Edit Selected {asset_type}")
        delete_button = QPushButton(f"Delete Selected {asset_type}")
        export_button = QPushButton("Export to CSV")
        
        # --- NEW: Reports Button and Menu ---
        reports_button = QPushButton("Reports")
        reports_menu = QMenu(self)
        reports_menu.addAction("Expired Warranty Report", self.show_expired_warranty_report)
        reports_menu.addAction("Assets with No Location", self.show_no_location_report)
        reports_menu.addAction("Assets by Location Chart", self.show_location_report)
        reports_button.setMenu(reports_menu)

        button_layout.addWidget(add_button)
        button_layout.addWidget(edit_button)
        button_layout.addWidget(delete_button)
        button_layout.addStretch() 
        button_layout.addWidget(reports_button) # Add new button
        button_layout.addWidget(export_button)
        layout.addLayout(button_layout)
        add_button.clicked.connect(self.add_asset)
        edit_button.clicked.connect(self.edit_asset)
        delete_button.clicked.connect(self.delete_asset)
        export_button.clicked.connect(self.export_to_csv)
        search_input.textChanged.connect(self.filter_assets)

    # --- NEW REPORTING METHODS ---
    def show_expired_warranty_report(self):
        conn = get_db_connection()
        all_assets = conn.execute("SELECT * FROM assets WHERE warranty_or_sub_end != ''").fetchall()
        conn.close()
        
        expired_assets = []
        today = datetime.now().date()
        
        for asset in all_assets:
            try:
                # Assuming date is in YYYY-MM-DD format
                end_date_str = asset['warranty_or_sub_end']
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if end_date < today:
                    expired_assets.append(asset)
            except (ValueError, TypeError):
                # Ignore assets with invalid or empty date formats
                continue
        
        headers = ["Name", "Asset Type", "Warranty Or Sub End"]
        dialog = ReportDialog("Expired Warranty/Subscription Report", headers, expired_assets, self)
        dialog.exec()

    def show_no_location_report(self):
        conn = get_db_connection()
        # Select assets where location is NULL or an empty string
        assets_no_location = conn.execute("SELECT * FROM assets WHERE location IS NULL OR location = ''").fetchall()
        conn.close()
        
        headers = ["Name", "Asset Type", "Vendor", "Notes"]
        dialog = ReportDialog("Assets with No Location", headers, assets_no_location, self)
        dialog.exec()

    def show_location_report(self):
        dialog = LocationReportDialog(self)
        dialog.exec()

    # --- EXISTING METHODS (UNCHANGED) ---
    def filter_assets(self):
        current_tab_index = self.tabs.currentIndex()
        table = self.hardware_table if current_tab_index == 0 else self.software_table
        search_text = (self.hardware_search if current_tab_index == 0 else self.software_search).text().lower()
        for row_num in range(table.rowCount()):
            match = False
            for col_num in range(table.columnCount()):
                item = table.item(row_num, col_num)
                if item and search_text in item.text().lower():
                    match = True
                    break
            table.setRowHidden(row_num, not match)
    def export_to_csv(self):
        current_tab_index = self.tabs.currentIndex()
        table = self.hardware_table if current_tab_index == 0 else self.software_table
        asset_type = "Hardware" if current_tab_index == 0 else "Software"
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", f"{asset_type}_Assets.csv", "CSV Files (*.csv)")
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
                    writer.writerow(headers)
                    for row_num in range(table.rowCount()):
                        if not table.isRowHidden(row_num):
                            row_data = [table.item(row_num, col_num).text() for col_num in range(table.columnCount())]
                            writer.writerow(row_data)
                QMessageBox.information(self, "Success", "Data exported successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export data: {e}")
    def load_assets(self):
        self.hardware_table.setRowCount(0)
        self.software_table.setRowCount(0)
        conn = get_db_connection()
        assets = conn.execute("SELECT * FROM assets ORDER BY name").fetchall()
        conn.close()
        for asset in assets:
            table = self.hardware_table if asset['asset_type'] == 'Hardware' else self.software_table
            row_position = table.rowCount()
            table.insertRow(row_position)
            table.setItem(row_position, 0, QTableWidgetItem(str(asset['id'])))
            table.setItem(row_position, 1, QTableWidgetItem(asset['name']))
            table.setItem(row_position, 2, QTableWidgetItem(asset['serial_or_license_key']))
            table.setItem(row_position, 3, QTableWidgetItem(asset['purchase_date']))
            table.setItem(row_position, 4, QTableWidgetItem(asset['warranty_or_sub_start']))
            table.setItem(row_position, 5, QTableWidgetItem(asset['warranty_or_sub_end']))
            table.setItem(row_position, 6, QTableWidgetItem(asset['location']))
            table.setItem(row_position, 7, QTableWidgetItem(asset['vendor']))
            table.setItem(row_position, 8, QTableWidgetItem(asset['bought_at']))
            table.setItem(row_position, 9, QTableWidgetItem(asset['notes']))
    def add_asset(self):
        dialog = AssetDialog(parent=self)
        if dialog.exec():
            data = dialog.get_data()
            conn = get_db_connection()
            conn.execute("INSERT INTO assets (asset_type, name, serial_or_license_key, purchase_date, warranty_or_sub_start, warranty_or_sub_end, location, vendor, bought_at, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (data['asset_type'], data['name'], data['serial_or_license_key'], data['purchase_date'], data['warranty_or_sub_start'], data['warranty_or_sub_end'], data['location'], data['vendor'], data['bought_at'], data['notes']))
            conn.commit()
            conn.close()
            self.load_assets()
    def edit_asset(self):
        current_tab_index = self.tabs.currentIndex()
        table = self.hardware_table if current_tab_index == 0 else self.software_table
        selected_row = table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Warning", "Please select an asset to edit.")
            return
        asset_id = int(table.item(selected_row, 0).text())
        conn = get_db_connection()
        asset_data = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        conn.close()
        if not asset_data:
            QMessageBox.critical(self, "Error", "Could not find the selected asset in the database.")
            return
        dialog = AssetDialog(asset_data=asset_data, parent=self)
        if dialog.exec():
            new_data = dialog.get_data()
            conn = get_db_connection()
            conn.execute("UPDATE assets SET asset_type = ?, name = ?, serial_or_license_key = ?, purchase_date = ?, warranty_or_sub_start = ?, warranty_or_sub_end = ?, location = ?, vendor = ?, bought_at = ?, notes = ? WHERE id = ?", (new_data['asset_type'], new_data['name'], new_data['serial_or_license_key'], new_data['purchase_date'], new_data['warranty_or_sub_start'], new_data['warranty_or_sub_end'], new_data['location'], new_data['vendor'], new_data['bought_at'], new_data['notes'], asset_id))
            conn.commit()
            conn.close()
            self.load_assets()
    def delete_asset(self):
        current_tab_index = self.tabs.currentIndex()
        table = self.hardware_table if current_tab_index == 0 else self.software_table
        selected_row = table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Warning", "Please select an asset to delete.")
            return
        asset_id = int(table.item(selected_row, 0).text())
        asset_name = table.item(selected_row, 1).text()
        reply = QMessageBox.question(self, 'Delete Asset', f"Are you sure you want to delete '{asset_name}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = get_db_connection()
            conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            conn.commit()
            conn.close()
            self.load_assets()

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = AssetTracker()
    window.show()
    sys.exit(app.exec())
