from flask import Flask, render_template, request, redirect, url_for, flash, session

from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db_connection

import qrcode
import os

from datetime import datetime


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

            if role == "passenger":

                return redirect(
                    url_for("passenger_search")
                )

            else:

                return redirect(
                    url_for("driver_dashboard")
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
        pickup_location = request.form.get("pickup_location")
        destination = request.form.get("destination")

        # Driver-specific data

        auto_number = request.form.get("auto_number")
        license_number = request.form.get("license_number")


        password_hash = generate_password_hash(password)


        connection = get_db_connection()

        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO users
                (
                    full_name,
                    email,
                    phone,
                    password_hash,
                    role,
                    pickup_location,
                    destination
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    full_name,
                    email,
                    phone,
                    password_hash,
                    role,
                    pickup_location if role == "passenger" else None,
                    destination if role == "passenger" else None
                )
            )

            user_id = cursor.lastrowid


            if role == "driver":
                # Create driver record
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

                driver_id = cursor.lastrowid

                # Create auto record
                cursor.execute(
                    """
                    INSERT INTO autos
                    (
                        driver_id,
                        auto_number,
                        capacity,
                        status
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        driver_id,
                        auto_number,
                        3,
                        "available"
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

            print(
                "Registration error:",
                error
            )

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

@app.route("/passenger/search", methods=["GET", "POST"])
def passenger_search():

    if "user_id" not in session:
        return redirect(url_for("login", role="passenger"))

    if session["role"] == "driver":
        return redirect(url_for("driver_dashboard"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # =========================
    # GET ALL LOCATIONS
    # =========================

    cursor.execute("""
        SELECT start_location, destination
        FROM routes
        ORDER BY start_location, destination
    """)

    route_rows = cursor.fetchall()

    locations = sorted(set(
        [row["start_location"] for row in route_rows]
        + [row["destination"] for row in route_rows]
    ))

    # =========================
    # GET LAST BOARDED TRIP
    # =========================

    cursor.execute("""
        SELECT
            t.id AS trip_id,
            a.auto_number,
            t.available_seats,
            t.status,
            r.route_name,
            r.start_location,
            r.destination,
            tp.boarded_at
        FROM trip_passengers tp

        JOIN trips t
            ON tp.trip_id = t.id

        JOIN autos a
            ON t.auto_id = a.id

        JOIN routes r
            ON t.route_id = r.id

        WHERE tp.passenger_id = %s

        ORDER BY tp.id DESC
        LIMIT 1
    """, (session["user_id"],))

    last_boarded = cursor.fetchone()

    # =========================
    # SEARCH AUTOS
    # =========================

    autos = []
    pickup = ""
    destination = ""

    if request.method == "POST":

        pickup = request.form["pickup_location"]
        destination = request.form["destination"]

        cursor.execute("""
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

            WHERE t.status = 'active'
              AND t.available_seats > 0
              AND LOWER(TRIM(r.start_location))
                    = LOWER(TRIM(%s))
              AND LOWER(TRIM(r.destination))
                    = LOWER(TRIM(%s))

            ORDER BY t.started_at DESC
        """, (pickup, destination))

        autos = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "passenger_search.html",
        locations=locations,
        autos=autos,
        pickup=pickup,
        destination=destination,
        last_boarded=last_boarded
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
        
     # Passenger goes to search page
    return redirect(
        url_for("passenger_search")
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
    
    
        # =========================
    # DASHBOARD STATISTICS
    # =========================

    # Total trips by this driver
    cursor.execute(
        """
        SELECT COUNT(*) AS total_trips
        FROM trips t
        JOIN autos a ON t.auto_id = a.id
        JOIN drivers d ON a.driver_id = d.id
        WHERE d.user_id = %s
        """,
        (session["user_id"],)
    )

    total_trips = cursor.fetchone()["total_trips"]


    # Completed trips
    cursor.execute(
        """
        SELECT COUNT(*) AS completed_trips
        FROM trips t
        JOIN autos a ON t.auto_id = a.id
        JOIN drivers d ON a.driver_id = d.id
        WHERE d.user_id = %s
          AND t.status = 'completed'
        """,
        (session["user_id"],)
    )

    completed_trips = cursor.fetchone()["completed_trips"]


    # Total passengers served
    cursor.execute(
        """
        SELECT COUNT(*) AS passengers_served
        FROM trip_passengers tp
        JOIN trips t ON tp.trip_id = t.id
        JOIN autos a ON t.auto_id = a.id
        JOIN drivers d ON a.driver_id = d.id
        WHERE d.user_id = %s
        """,
        (session["user_id"],)
    )

    passengers_served = cursor.fetchone()["passengers_served"]


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
    active_trip=active_trip,
    total_trips=total_trips,
    completed_trips=completed_trips,
    passengers_served=passengers_served
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
            SELECT
                id
            FROM trips
            WHERE auto_id = %s
            AND status IN ('active', 'full')
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

    trip_id = request.args.get("trip_id")

    if not trip_id:
        return "Please select an auto first.", 400

    return render_template(
        "scan_qr.html",
        selected_trip_id=trip_id
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

            return render_template(
        "boarding_already.html",
        trip=trip
    )


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

        boarding_time = datetime.now().strftime(
            "%d-%m-%Y %I:%M:%S %p"
        )

        return render_template(
            "boarding_success.html",
            trip=trip,
            remaining_seats=new_seats,
            boarding_time=boarding_time
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
# PASSENGER TRIP HISTORY
# =========================

@app.route("/passenger/trips")
def passenger_trips():

    if "user_id" not in session:
        return redirect(url_for("login", role="passenger"))

    if session["role"] != "passenger":
        return "Only passengers can view trip history.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            tp.id AS boarding_id,
            tp.trip_id,
            a.auto_number,
            r.route_name,
            r.start_location,
            r.destination,
            tp.boarded_at,
            t.status
        FROM trip_passengers tp

        JOIN trips t
            ON tp.trip_id = t.id

        JOIN autos a
            ON t.auto_id = a.id

        JOIN routes r
            ON t.route_id = r.id

        WHERE tp.passenger_id = %s

        ORDER BY tp.id DESC
    """, (session["user_id"],))

    trips = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "passenger_trips.html",
        trips=trips
    )
# =========================
# LOGOUT
# =========================

@app.route("/driver/trip/<int:trip_id>/passengers")
def driver_trip_passengers(trip_id):

    if "user_id" not in session:
        return redirect(url_for("login", role="driver"))

    if session["role"] != "driver":
        return "Only drivers can view passengers.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Get trip information
    cursor.execute("""
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
    """, (trip_id,))

    trip = cursor.fetchone()

    if not trip:
        cursor.close()
        connection.close()
        return "Trip not found.", 404

    # Get passengers who boarded
    cursor.execute("""
        SELECT
            u.id AS passenger_id,
            u.full_name,
            u.email,
            tp.boarded_at
        FROM trip_passengers tp

        JOIN users u
            ON tp.passenger_id = u.id

        WHERE tp.trip_id = %s

        ORDER BY tp.boarded_at ASC
    """, (trip_id,))

    passengers = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "driver_trip_passengers.html",
        trip=trip,
        passengers=passengers
    )

@app.route("/driver/end-trip/<int:trip_id>", methods=["POST"])
def end_trip(trip_id):

    if "user_id" not in session:
        return redirect(url_for("login", role="driver"))

    if session["role"] != "driver":
        return "Access denied", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # Check that this trip belongs to the logged-in driver
        cursor.execute(
            """
            SELECT t.id
            FROM trips t
            JOIN autos a
                ON t.auto_id = a.id
            JOIN drivers d
                ON a.driver_id = d.id
            WHERE t.id = %s
              AND d.user_id = %s
            """,
            (trip_id, session["user_id"])
        )

        trip = cursor.fetchone()

        if not trip:
            flash("Trip not found.")
            return redirect(url_for("driver_dashboard"))

        # End the trip
        cursor.execute(
    """
    UPDATE trips
    SET status = 'completed',
        ended_at = NOW()
    WHERE id = %s
    """,
    (trip_id,)
)

        connection.commit()

        flash("Trip ended successfully.")

        return redirect(url_for("driver_dashboard"))

    except Exception as e:

        connection.rollback()

        print("END TRIP ERROR:", e)

        flash("Could not end the trip.")

        return redirect(url_for("driver_dashboard"))

    finally:

        cursor.close()
        connection.close()
        
@app.route("/driver/trips")
def driver_trips():

    if "user_id" not in session:
        return redirect(url_for("login", role="driver"))

    if session["role"] != "driver":
        return "Access denied", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            t.id AS trip_id,
            t.available_seats,
            t.status,
            t.started_at,
            t.ended_at,

            a.auto_number,

            r.route_name,
            r.start_location,
            r.destination

        FROM trips t

        JOIN autos a
            ON t.auto_id = a.id

        JOIN routes r
            ON t.route_id = r.id

        JOIN drivers d
            ON a.driver_id = d.id

        WHERE d.user_id = %s

        ORDER BY t.id DESC
    """, (session["user_id"],))

    trips = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "driver_trips.html",
        trips=trips
    )
@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login", role="passenger")
    )
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )