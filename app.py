from flask import Flask, render_template, request, redirect, url_for, flash, session

from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db_connection

import qrcode
import os


app = Flask(__name__)

app.secret_key = "smart-auto-development-key"


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return render_template("index.html")


# =========================
# LOGIN PAGE
# =========================

@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):

    if role not in ["passenger", "driver"]:
        return "Invalid role", 400


    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]


        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)


        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = %s
            AND role = %s
            """,
            (email, role)
        )


        user = cursor.fetchone()


        cursor.close()
        connection.close()


        if user and check_password_hash(
            user["password_hash"],
            password
        ):

            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["role"] = user["role"]


            return redirect(
                url_for("dashboard")
            )


        flash("Invalid email or password.")


    return render_template(
        "login.html",
        role=role
    )


# =========================
# REGISTER
# =========================

@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):

    if role not in ["passenger", "driver"]:
        return "Invalid role", 400


    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]


        # Driver-specific data

        auto_number = request.form.get("auto_number")
        license_number = request.form.get("license_number")


        password_hash = generate_password_hash(password)


        connection = get_db_connection()

        cursor = connection.cursor()


        try:

            # Insert user

            cursor.execute(
                """
                INSERT INTO users
                (
                    full_name,
                    email,
                    phone,
                    password_hash,
                    role
                )

                VALUES (%s, %s, %s, %s, %s)
                """,

                (
                    full_name,
                    email,
                    phone,
                    password_hash,
                    role
                )
            )


            user_id = cursor.lastrowid


            # Driver information

            if role == "driver":

                cursor.execute(
                    """
                    INSERT INTO drivers
                    (
                        user_id,
                        license_number,
                        auto_number
                    )

                    VALUES (%s, %s, %s)
                    """,

                    (
                        user_id,
                        license_number,
                        auto_number
                    )
                )


            connection.commit()


            flash(
                "Registration successful! Please login."
            )


            return redirect(
                url_for("login", role=role)
            )


        except Exception as error:

            connection.rollback()

            print("Registration error:", error)

            flash(
                "Registration failed. Email, phone or auto number may already exist."
            )


        finally:

            cursor.close()
            connection.close()


    return render_template(
        "register.html",
        role=role
    )


# =========================
# PASSENGER DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(
            url_for("login", role="passenger")
        )

    # Driver goes to driver dashboard
    if session["role"] == "driver":
        return redirect(
            url_for("driver_dashboard")
        )

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Get active and full trips
    cursor.execute(
        """
        SELECT
            t.id AS trip_id,
            a.auto_number,
            a.capacity,
            t.available_seats,
            t.status,
            r.route_name,
            r.start_location,
            r.destination,
            r.estimated_minutes
        FROM trips t
        JOIN autos a
            ON t.auto_id = a.id
        JOIN routes r
            ON t.route_id = r.id
        WHERE t.status IN ('active', 'full')
        ORDER BY t.started_at DESC
        """
    )

    trips = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "passenger_dashboard.html",
        trips=trips
    )


# =========================
# DRIVER DASHBOARD
# =========================

@app.route("/driver/dashboard")
def driver_dashboard():

    if "user_id" not in session:

        return redirect(
            url_for(
                "login",
                role="driver"
            )
        )

    if session["role"] != "driver":

        return "Access denied", 403

    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)

    # =========================
    # GET DRIVER'S AUTO
    # =========================

    cursor.execute(
        """
        SELECT
            d.id AS driver_id,
            d.auto_number
        FROM drivers d
        WHERE d.user_id = %s
        """,
        (session["user_id"],)
    )

    driver = cursor.fetchone()


    # =========================
    # GET ROUTES
    # =========================

    cursor.execute(
        """
        SELECT *
        FROM routes
        ORDER BY route_name
        """
    )

    routes = cursor.fetchall()


    # =========================
    # GET ACTIVE TRIP
    # =========================

    cursor.execute(
        """
        SELECT
            t.id AS trip_id,
            t.available_seats,
            t.status,
            t.started_at,

            r.route_name,
            r.start_location,
            r.destination,

            a.auto_number,
            a.capacity

        FROM trips t

        JOIN autos a
            ON t.auto_id = a.id

        JOIN drivers d
            ON a.driver_id = d.id

        JOIN routes r
            ON t.route_id = r.id

        WHERE d.user_id = %s
        AND t.status IN ('active', 'full')

        ORDER BY t.started_at DESC

        LIMIT 1
        """,
        (session["user_id"],)
    )

    active_trip = cursor.fetchone()


    cursor.close()
    connection.close()


    # =========================
    # AUTO NUMBER
    # =========================

    auto_number = (
        driver["auto_number"]
        if driver
        else "Not registered"
    )


    # =========================
    # DRIVER DASHBOARD
    # =========================

    return render_template(
        "driver_dashboard.html",
        auto_number=auto_number,
        routes=routes,
        active_trip=active_trip
    )



    
    
# =========================
# START TRIP
# =========================

@app.route("/driver/start-trip", methods=["POST"])
def start_trip():
    


    print("========== START TRIP ROUTE CALLED ==========")
    print("USER ID:", session.get("user_id"))
    print("ROLE:", session.get("role"))
    print("FORM DATA:", request.form)

    if "user_id" not in session:
        return redirect(url_for("login", role="driver"))


    if session["role"] != "driver":
        return "Access denied", 403

    route_id = request.form["route_id"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # =========================
        # GET DRIVER'S AUTO
        # =========================

        cursor.execute(
            """
            SELECT
                a.id AS auto_id,
                a.auto_number,
                a.capacity
            FROM autos a
            JOIN drivers d
                ON a.driver_id = d.id
            WHERE d.user_id = %s
            """,
            (session["user_id"],)
        )

        auto = cursor.fetchone()

        if not auto:

            flash("Auto is not registered in the system.")

            return redirect(
                url_for("driver_dashboard")
            )


        # =========================
        # CHECK ACTIVE TRIP
        # =========================

        cursor.execute(
            """
            SELECT id
            FROM trips
            WHERE auto_id = %s
            AND status = 'active'
            """,
            (auto["auto_id"],)
        )

        active_trip = cursor.fetchone()

        if active_trip:

            flash("You already have an active trip.")

            return redirect(
                url_for("driver_dashboard")
            )


        # =========================
        # CREATE TRIP
        # =========================

        cursor.execute(
            """
            INSERT INTO trips
            (
                auto_id,
                route_id,
                available_seats,
                status,
                started_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (
                auto["auto_id"],
                route_id,
                auto["capacity"],
                "active"
            )
        )

        trip_id = cursor.lastrowid


        connection.commit()


        print("Trip created:", trip_id)


        # =========================
        # GENERATE QR CODE
        # =========================

        qr_data = f"https://192.168.0.105:5000/board/{trip_id}"

        qr = qrcode.make(qr_data)


        # Absolute path to static/qr

        qr_folder = os.path.join(
            app.root_path,
            "static",
            "qr"
        )


        os.makedirs(
            qr_folder,
            exist_ok=True
        )


        qr_path = os.path.join(
            qr_folder,
            f"trip_{trip_id}.png"
        )


        qr.save(qr_path)


        print("QR saved at:", qr_path)


        flash("Trip started successfully!")


        # Open trip page

        return redirect(
            url_for(
                "trip_page",
                trip_id=trip_id
            )
        )


    except Exception as error:

        connection.rollback()

        print(
            "START TRIP ERROR:",
            error
        )

        flash("Unable to start trip.")


    finally:

        cursor.close()
        connection.close()


    return redirect(
        url_for("driver_dashboard")
    )
    
    # =========================
# TRIP PAGE
# =========================

@app.route("/driver/trip/<int:trip_id>")
def trip_page(trip_id):

    if "user_id" not in session:
        return redirect(
            url_for("login", role="driver")
        )

    if session["role"] != "driver":
        return "Access denied", 403


    connection = get_db_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    cursor.execute(
        """
        SELECT
            t.id AS trip_id,
            t.available_seats,
            t.status,
            t.started_at,

            a.auto_number,
            a.capacity,

            r.route_name,
            r.start_location,
            r.destination

        FROM trips t

        JOIN autos a
            ON t.auto_id = a.id

        JOIN drivers d
            ON a.driver_id = d.id

        JOIN routes r
            ON t.route_id = r.id

        WHERE t.id = %s
        AND d.user_id = %s
        """,
        (
            trip_id,
            session["user_id"]
        )
    )


    trip = cursor.fetchone()


    cursor.close()
    connection.close()


    if not trip:
        return "Trip not found", 404


    return render_template(
        "trip.html",
        trip=trip
    )
    
    # =========================
# SCAN QR PAGE
# =========================

@app.route("/scan-qr")
def scan_qr():

    if "user_id" not in session:

        return redirect(
            url_for("login", role="passenger")
        )


    if session["role"] != "passenger":

        return "Only passengers can scan QR codes.", 403


    return render_template(
        "scan_qr.html"
    )
    
    # =========================
# BOARD TRIP
# =========================

@app.route("/board/<int:trip_id>")
def board_trip(trip_id):

    # Passenger must be logged in
    if "user_id" not in session:
        return redirect(
            url_for("login", role="passenger")
        )

    # Only passenger can board
    if session["role"] != "passenger":
        return "Only passengers can board the auto.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # =========================
        # GET TRIP
        # =========================

        cursor.execute(
            """
            SELECT
                t.id AS trip_id,
                t.available_seats,
                t.status,
                a.auto_number,
                r.route_name,
                r.start_location,
                r.destination
            FROM trips t

            JOIN autos a
                ON t.auto_id = a.id

            JOIN routes r
                ON t.route_id = r.id

            WHERE t.id = %s
            """,
            (trip_id,)
        )

        trip = cursor.fetchone()

        if not trip:
            return "Trip not found.", 404


        # =========================
        # CHECK TRIP STATUS
        # =========================

        if trip["status"] not in ["active"]:
            return "This trip is no longer available for boarding."


        # =========================
        # CHECK SEATS
        # =========================

        if trip["available_seats"] <= 0:

            return "Sorry, this auto is FULL."


        # =========================
        # CHECK DUPLICATE BOARDING
        # =========================

        cursor.execute(
            """
            SELECT id
            FROM trip_passengers
            WHERE trip_id = %s
            AND passenger_id = %s
            """,
            (
                trip_id,
                session["user_id"]
            )
        )

        already_boarded = cursor.fetchone()

        if already_boarded:

            return "You have already boarded this auto."


        # =========================
        # INSERT PASSENGER
        # =========================

        cursor.execute(
            """
            INSERT INTO trip_passengers
            (
                trip_id,
                passenger_id
            )
            VALUES (%s, %s)
            """,
            (
                trip_id,
                session["user_id"]
            )
        )


        # =========================
        # DECREASE SEAT
        # =========================

        new_seats = trip["available_seats"] - 1

        new_status = "active"

        if new_seats == 0:
            new_status = "full"


        cursor.execute(
            """
            UPDATE trips
            SET
                available_seats = %s,
                status = %s
            WHERE id = %s
            """,
            (
                new_seats,
                new_status,
                trip_id
            )
        )


        connection.commit()


        return render_template(
            "boarding_success.html",
            trip=trip,
            remaining_seats=new_seats
        )


    except Exception as error:

        connection.rollback()

        print(
            "BOARDING ERROR:",
            error
        )

        return "Unable to board the auto."


    finally:

        cursor.close()
        connection.close()
    
# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )