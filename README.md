==============================
# Business Asset Tracker
==============================

**Author:** Tim
**Date:** July 2, 2025
**Version:** 1.0.0

### Description

This is a simple desktop application designed to help small businesses track their hardware and software assets. It provides a clean, tabbed interface to view, add, edit, delete, and search for company assets, ensuring important information like serial numbers, purchase dates, and vendor details are always organized and accessible.

The application uses PySide6 for the graphical user interface (GUI) and SQLite for lightweight, local database storage.


### Features

* **Hardware & Software Tabs:** Keep hardware and software assets organized in separate lists.
* **Add, Edit, & Delete:** Full CRUD (Create, Read, Update, Delete) functionality for managing your asset list.
* **Persistent Storage:** All asset data is saved in a local SQLite database file (`assets.db`), so your information is preserved between sessions.
* **Live Search/Filter:** Instantly filter the asset lists by typing into the search bar. The filter checks all fields for a match.
* **Export to CSV:** Export the currently displayed list of hardware or software assets to a CSV file, which can be opened in any spreadsheet program like Microsoft Excel or Google Sheets.
* **Detailed Tracking:** Stores key information for each asset, including:
    * Name
    * Serial/License Key
    * Purchase Date
    * Warranty/Subscription Start & End Dates
    * Location
    * Vendor
    * Purchase Location ("Bought At")
    * Notes


### Requirements

To run this application, you will need:
* Python 3.x
* PySide6 library


### Setup and Installation

Follow these steps to get the application running on your local machine.

1.  **Install Python:** If you don't already have Python installed, download it from [https://www.python.org/downloads/](https://www.python.org/downloads/).

2.  **Install PySide6:** Open your terminal or command prompt and run the following command to install the required library:
    ```
    pip install PySide6
    ```

3.  **Set up the Database:**
    * Ensure the `database_setup.py` script is in the same directory as `app.py`.
    * Run the setup script once from your terminal to create the `assets.db` database file:
    ```
    python database_setup.py
    ```
    * You only need to do this the very first time you set up the application or if you want to start with a fresh, empty database.


### How to Run the Application

Once the setup is complete, you can launch the main application with this command:

python app.py
The Business Asset Tracker window should appear, ready for you to start managing your assets.


