import os, sqlite3, secrets
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DB = os.path.join(os.path.dirname(__file__), "avtoprime.db")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
          email TEXT UNIQUE NOT NULL, phone TEXT, password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'client', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS brands(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS cars(
          id INTEGER PRIMARY KEY AUTOINCREMENT, brand_id INTEGER REFERENCES brands(id),
          model TEXT NOT NULL, year INTEGER NOT NULL, mileage INTEGER NOT NULL,
          price INTEGER NOT NULL, body_type TEXT, transmission TEXT, engine_type TEXT,
          color TEXT, description TEXT, image_url TEXT, status TEXT DEFAULT 'available');
        CREATE TABLE IF NOT EXISTS applications(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id),
          car_id INTEGER REFERENCES cars(id), type TEXT NOT NULL, status TEXT DEFAULT 'new',
          comment TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS favorites(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id),
          car_id INTEGER REFERENCES cars(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, car_id));
        CREATE TABLE IF NOT EXISTS credit_calculations(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id),
          car_id INTEGER REFERENCES cars(id), loan_amount REAL, term_months INTEGER,
          interest_rate REAL, monthly_payment REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS admin_logs(
          id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT,
          entity_type TEXT, entity_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if not con.execute("SELECT id FROM users WHERE email='admin@avtoprime.ru'").fetchone():
            con.execute("INSERT INTO users(full_name,email,phone,password_hash,role) VALUES(?,?,?,?,?)",
                ("Администратор", "admin@avtoprime.ru", "", generate_password_hash("admin123"), "admin"))
        if con.execute("SELECT COUNT(*) FROM cars").fetchone()[0] == 0:
            seeds = [
              ("Mercedes-Benz","E-Класс",2022,32000,5850000,"Седан","Автомат","Бензин","Чёрный","Комфортный бизнес-седан с современными системами безопасности.","https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/0_Mercedes-Benz_W213_Facelift_0.jpg/960px-0_Mercedes-Benz_W213_Facelift_0.jpg"),
              ("BMW","5 серии",2021,41000,4990000,"Седан","Автомат","Бензин","Серый","Динамичный седан с отличной управляемостью.","https://upload.wikimedia.org/wikipedia/commons/thumb/d/d1/2021_BMW_5-Series_520d_M_Sport.jpg/960px-2021_BMW_5-Series_520d_M_Sport.jpg"),
              ("Toyota","Camry",2023,18000,3890000,"Седан","Автомат","Бензин","Белый","Надёжный и практичный автомобиль для города и путешествий.","https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Toyota_Camry_Sonoma_2023.jpg/960px-Toyota_Camry_Sonoma_2023.jpg"),
              ("Audi","Q5",2022,27000,6200000,"Кроссовер","Робот","Бензин","Синий","Премиальный кроссовер с полным приводом.","https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/2022_Audi_Q5_quattro_Premium_Plus_45TFSI_in_Silver%2C_rear_right.jpg/960px-2022_Audi_Q5_quattro_Premium_Plus_45TFSI_in_Silver%2C_rear_right.jpg"),
              ("Kia","K5",2022,29000,2790000,"Седан","Автомат","Бензин","Красный","Стильный городской седан с богатым оснащением.","https://upload.wikimedia.org/wikipedia/commons/thumb/1/1e/%E2%80%9822_Kia_K5.jpg/960px-%E2%80%9822_Kia_K5.jpg"),
              ("Volkswagen","Tiguan",2021,52000,3150000,"Кроссовер","Робот","Бензин","Белый","Универсальный семейный кроссовер.","https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/2021_Volkswagen_Tiguan_Life.jpg/960px-2021_Volkswagen_Tiguan_Life.jpg"),
            ]
            for brand, model, year, mileage, price, body, trans, engine, color, desc, image in seeds:
                cur = con.execute("INSERT OR IGNORE INTO brands(name) VALUES(?)", (brand,))
                bid = con.execute("SELECT id FROM brands WHERE name=?", (brand,)).fetchone()["id"]
                con.execute("""INSERT INTO cars(brand_id,model,year,mileage,price,body_type,transmission,engine_type,color,description,image_url)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(bid,model,year,mileage,price,body,trans,engine,color,desc,image))

        # Always refresh demo car photos, including existing databases (Wikimedia Commons).
        local_images = {
            ("Mercedes-Benz", "E-Класс"): "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/0_Mercedes-Benz_W213_Facelift_0.jpg/960px-0_Mercedes-Benz_W213_Facelift_0.jpg",
            ("BMW", "5 серии"): "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d1/2021_BMW_5-Series_520d_M_Sport.jpg/960px-2021_BMW_5-Series_520d_M_Sport.jpg",
            ("Toyota", "Camry"): "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Toyota_Camry_Sonoma_2023.jpg/960px-Toyota_Camry_Sonoma_2023.jpg",
            ("Audi", "Q5"): "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/2022_Audi_Q5_quattro_Premium_Plus_45TFSI_in_Silver%2C_rear_right.jpg/960px-2022_Audi_Q5_quattro_Premium_Plus_45TFSI_in_Silver%2C_rear_right.jpg",
            ("Kia", "K5"): "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1e/%E2%80%9822_Kia_K5.jpg/960px-%E2%80%9822_Kia_K5.jpg",
            ("Volkswagen", "Tiguan"): "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/2021_Volkswagen_Tiguan_Life.jpg/960px-2021_Volkswagen_Tiguan_Life.jpg",
        }
        for (brand_name, model_name), image_path in local_images.items():
            con.execute("UPDATE cars SET image_url=? WHERE model=? AND brand_id=(SELECT id FROM brands WHERE name=?)",
                        (image_path, model_name, brand_name))

        # Дополнительные 5 автомобилей: две новые модели и три варианта уже представленных моделей.
        extra_cars = [
            ("BMW", "X5", 2021, 36000, 7350000, "Кроссовер", "Автомат", "Бензин", "Чёрный",
             "Полноразмерный премиальный кроссовер BMW X5.",
             "https://commons.wikimedia.org/wiki/Special:FilePath/BMW_X5_2021.jpg"),
            ("Porsche", "Cayenne", 2022, 24000, 9850000, "Кроссовер", "Автомат", "Бензин", "Серый",
             "Спортивный премиальный кроссовер Porsche Cayenne.",
             "https://commons.wikimedia.org/wiki/Special:FilePath/Porsche_Cayenne_3.jpg"),
            ("Volkswagen", "Tiguan R-Line", 2023, 21000, 3790000, "Кроссовер", "Робот", "Бензин", "Белый",
             "Volkswagen Tiguan в спортивном исполнении R-Line.",
             "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/2021_Volkswagen_Tiguan_Life.jpg/960px-2021_Volkswagen_Tiguan_Life.jpg"),
            ("Kia", "K5 GT-Line", 2023, 17000, 3190000, "Седан", "Автомат", "Бензин", "Красный",
             "Kia K5 в комплектации GT-Line с выразительным дизайном.",
             "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1e/%E2%80%9822_Kia_K5.jpg/960px-%E2%80%9822_Kia_K5.jpg"),
            ("Audi", "Q5 quattro", 2021, 44000, 5790000, "Кроссовер", "Робот", "Бензин", "Серебристый",
             "Audi Q5 с полным приводом quattro.",
             "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/2022_Audi_Q5_quattro_Premium_Plus_45TFSI_in_Silver%2C_rear_right.jpg/960px-2022_Audi_Q5_quattro_Premium_Plus_45TFSI_in_Silver%2C_rear_right.jpg"),
            ("Mercedes-Benz", "S 55 AMG W220", 2003, 118000, 2350000, "Седан", "Автомат", "V8 Kompressor 5.4 л (5.5)", "Чёрный",
             "Mercedes-Benz S 55 AMG поколения W220. Двигатель V8 Kompressor объёмом 5.4 л (в торговом обозначении — 5.5). Чёрный кузов и тёмные стёкла на реальной фотографии.",
             "https://upload.wikimedia.org/wikipedia/commons/0/09/Mercedes_S-Class_W220_black_%281%29.jpg"),
        ]
        for brand, model, year, mileage, price, body, trans, engine, color, desc, image in extra_cars:
            con.execute("INSERT OR IGNORE INTO brands(name) VALUES(?)", (brand,))
            bid = con.execute("SELECT id FROM brands WHERE name=?", (brand,)).fetchone()["id"]
            exists = con.execute(
                "SELECT id FROM cars WHERE brand_id=? AND model=? AND year=?",
                (bid, model, year)
            ).fetchone()
            if not exists:
                con.execute("""INSERT INTO cars(brand_id,model,year,mileage,price,body_type,transmission,engine_type,color,description,image_url)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (bid, model, year, mileage, price, body, trans, engine, color, desc, image))

def current_user():
    if "user_id" not in session: return None
    with db() as con:
        return con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Для этого действия войдите в аккаунт.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user["role"] not in ("admin","manager"):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_user():
    return {"user": current_user()}

@app.route("/")
def index():
    with db() as con:
        cars = con.execute("""SELECT cars.*, brands.name brand FROM cars JOIN brands ON brands.id=cars.brand_id
            WHERE cars.status='available' ORDER BY cars.id DESC LIMIT 9""").fetchall()
        count = con.execute("SELECT COUNT(*) FROM cars WHERE status='available'").fetchone()[0]
    return render_template("index.html", cars=cars, count=count)

@app.route("/catalog")
def catalog():
    q = request.args.get("q","").strip()
    brand = request.args.get("brand","")
    body = request.args.get("body","")
    trans = request.args.get("trans","")
    min_price = request.args.get("min_price","")
    max_price = request.args.get("max_price","")
    sort = request.args.get("sort","new")
    sql = """SELECT cars.*, brands.name brand FROM cars JOIN brands ON brands.id=cars.brand_id
             WHERE cars.status='available'"""
    params=[]
    if q: sql += " AND (brands.name LIKE ? OR cars.model LIKE ?)"; params += [f"%{q}%",f"%{q}%"]
    if brand: sql += " AND brands.name=?"; params.append(brand)
    if body: sql += " AND body_type=?"; params.append(body)
    if trans: sql += " AND transmission=?"; params.append(trans)
    if min_price.isdigit(): sql += " AND price>=?"; params.append(int(min_price))
    if max_price.isdigit(): sql += " AND price<=?"; params.append(int(max_price))
    order = {"price_up":"price ASC","price_down":"price DESC","year":"year DESC","mileage":"mileage ASC"}.get(sort,"cars.id DESC")
    sql += " ORDER BY " + order
    with db() as con:
        cars=con.execute(sql,params).fetchall()
        brands=con.execute("SELECT name FROM brands ORDER BY name").fetchall()
    favorite_ids=set()
    u=current_user()
    if u:
        with db() as con:
            favorite_ids={r["car_id"] for r in con.execute("SELECT car_id FROM favorites WHERE user_id=?",(u["id"],))}
    return render_template("catalog.html",cars=cars,brands=brands,favorite_ids=favorite_ids,
       filters=dict(q=q,brand=brand,body=body,trans=trans,min_price=min_price,max_price=max_price,sort=sort))

@app.route("/car/<int:car_id>")
def car_detail(car_id):
    with db() as con:
        car=con.execute("SELECT cars.*,brands.name brand FROM cars JOIN brands ON brands.id=cars.brand_id WHERE cars.id=?",(car_id,)).fetchone()
    if not car: abort(404)
    return render_template("car.html",car=car)

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form.get("full_name","").strip()
        email=request.form.get("email","").strip().lower()
        phone=request.form.get("phone","").strip()
        password=request.form.get("password","")
        if not name or "@" not in email or len(password)<6 or (phone and len(phone)<6):
            flash("Проверьте имя, email, телефон и пароль (не менее 6 символов).","error")
        else:
            try:
                with db() as con:
                    con.execute("INSERT INTO users(full_name,email,phone,password_hash) VALUES(?,?,?,?)",
                       (name,email,phone,generate_password_hash(password)))
                    uid=con.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()["id"]
                session["user_id"]=uid
                flash("Аккаунт создан. Добро пожаловать!","success")
                return redirect(url_for("account"))
            except sqlite3.IntegrityError:
                flash("Пользователь с таким email уже существует.","error")
    return render_template("auth.html",mode="register")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        with db() as con:
            u=con.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if u and check_password_hash(u["password_hash"],password):
            session["user_id"]=u["id"]
            return redirect(url_for("admin") if u["role"] in ("admin","manager") else url_for("account"))
        flash("Неверный email или пароль.","error")
    return render_template("auth.html",mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/account")
@login_required
def account():
    u=current_user()
    with db() as con:
        apps=con.execute("""SELECT applications.*,brands.name brand,cars.model,cars.year FROM applications
          JOIN cars ON cars.id=applications.car_id JOIN brands ON brands.id=cars.brand_id
          WHERE applications.user_id=? ORDER BY applications.created_at DESC""",(u["id"],)).fetchall()
        favs=con.execute("""SELECT cars.*,brands.name brand FROM favorites JOIN cars ON cars.id=favorites.car_id
          JOIN brands ON brands.id=cars.brand_id WHERE favorites.user_id=?""",(u["id"],)).fetchall()
    return render_template("account.html",apps=apps,favs=favs)

@app.route("/favorite/<int:car_id>",methods=["POST"])
@login_required
def favorite(car_id):
    u=current_user()
    with db() as con:
        row=con.execute("SELECT id FROM favorites WHERE user_id=? AND car_id=?",(u["id"],car_id)).fetchone()
        if row: con.execute("DELETE FROM favorites WHERE id=?",(row["id"],))
        else: con.execute("INSERT OR IGNORE INTO favorites(user_id,car_id) VALUES(?,?)",(u["id"],car_id))
    return redirect(request.referrer or url_for("catalog"))

@app.route("/application/<int:car_id>",methods=["POST"])
@login_required
def application(car_id):
    u=current_user()
    kind=request.form.get("type","purchase")
    comment=request.form.get("comment","").strip()
    if kind not in ("purchase","test_drive","trade_in"): kind="purchase"
    with db() as con:
        car=con.execute("SELECT id FROM cars WHERE id=? AND status='available'",(car_id,)).fetchone()
        if not car: flash("Автомобиль уже недоступен.","error")
        else:
            con.execute("INSERT INTO applications(user_id,car_id,type,comment) VALUES(?,?,?,?)",(u["id"],car_id,kind,comment))
            flash("Заявка успешно отправлена! Менеджер скоро свяжется с вами.","success")
    return redirect(url_for("account"))

@app.route("/credit/calculate",methods=["POST"])
def credit_calculate():
    data=request.get_json(silent=True) or {}
    try:
        amount=float(data.get("amount",0)); months=int(data.get("months",0)); rate=float(data.get("rate",0))
        if amount<=0 or months<=0 or months>360 or rate<0 or rate>100: raise ValueError()
        monthly_rate=rate/1200
        payment=amount/months if monthly_rate==0 else amount*monthly_rate/(1-(1+monthly_rate)**(-months))
        u=current_user()
        if u:
            with db() as con:
                con.execute("INSERT INTO credit_calculations(user_id,car_id,loan_amount,term_months,interest_rate,monthly_payment) VALUES(?,?,?,?,?,?)",
                    (u["id"],data.get("car_id"),amount,months,rate,round(payment,2)))
        return jsonify(ok=True,monthly_payment=round(payment,2),total=round(payment*months,2),
                       source="Расчёт выполнен встроенным модулем предварительной оценки. Условия банка уточняются у менеджера.")
    except (ValueError,TypeError):
        return jsonify(ok=False,error="Проверьте сумму, срок и процентную ставку."),400

@app.route("/admin")
@admin_required
def admin():
    with db() as con:
        apps=con.execute("""SELECT applications.*,users.full_name,users.phone,brands.name brand,cars.model FROM applications
          JOIN users ON users.id=applications.user_id JOIN cars ON cars.id=applications.car_id
          JOIN brands ON brands.id=cars.brand_id ORDER BY applications.created_at DESC""").fetchall()
        cars=con.execute("SELECT cars.*,brands.name brand FROM cars JOIN brands ON brands.id=cars.brand_id ORDER BY cars.id DESC").fetchall()
        total=con.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        new=con.execute("SELECT COUNT(*) FROM applications WHERE status='new'").fetchone()[0]
        popular=con.execute("""SELECT brands.name brand,cars.model,COUNT(applications.id) cnt FROM applications
          JOIN cars ON cars.id=applications.car_id JOIN brands ON brands.id=cars.brand_id
          GROUP BY cars.id ORDER BY cnt DESC LIMIT 5""").fetchall()
    return render_template("admin.html",apps=apps,cars=cars,total=total,new=new,popular=popular)

@app.route("/admin/car",methods=["POST"])
@admin_required
def admin_add_car():
    f=request.form
    try:
        year=int(f.get("year")); mileage=int(f.get("mileage")); price=int(f.get("price"))
        if not (1900<=year<=2100 and mileage>=0 and price>0): raise ValueError()
        with db() as con:
            con.execute("INSERT OR IGNORE INTO brands(name) VALUES(?)",(f["brand"].strip(),))
            bid=con.execute("SELECT id FROM brands WHERE name=?",(f["brand"].strip(),)).fetchone()["id"]
            cur=con.execute("""INSERT INTO cars(brand_id,model,year,mileage,price,body_type,transmission,engine_type,color,description,image_url)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(bid,f["model"],year,mileage,price,f.get("body_type"),f.get("transmission"),f.get("engine_type"),f.get("color"),f.get("description"),f.get("image_url")))
            con.execute("INSERT INTO admin_logs(admin_id,action,entity_type,entity_id) VALUES(?,?,?,?)",(current_user()["id"],"Добавлен автомобиль","car",cur.lastrowid))
        flash("Автомобиль добавлен.","success")
    except (ValueError,KeyError):
        flash("Проверьте заполнение полей автомобиля.","error")
    return redirect(url_for("admin"))

@app.route("/admin/car/<int:car_id>/delete",methods=["POST"])
@admin_required
def admin_delete_car(car_id):
    with db() as con:
        con.execute("UPDATE cars SET status='archived' WHERE id=?",(car_id,))
        con.execute("INSERT INTO admin_logs(admin_id,action,entity_type,entity_id) VALUES(?,?,?,?)",(current_user()["id"],"Архивирован автомобиль","car",car_id))
    flash("Автомобиль перемещён в архив.","success")
    return redirect(url_for("admin"))

@app.route("/admin/application/<int:app_id>",methods=["POST"])
@admin_required
def admin_update_application(app_id):
    status=request.form.get("status")
    if status not in ("new","in_progress","done","rejected"): abort(400)
    with db() as con:
        con.execute("UPDATE applications SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(status,app_id))
        con.execute("INSERT INTO admin_logs(admin_id,action,entity_type,entity_id) VALUES(?,?,?,?)",(current_user()["id"],"Изменён статус заявки","application",app_id))
    flash("Статус заявки обновлён.","success")
    return redirect(url_for("admin"))

@app.errorhandler(403)
def forbidden(e): return render_template("message.html",title="Доступ запрещён",message="Эта страница доступна только менеджеру или администратору."),403
@app.errorhandler(404)
def not_found(e): return render_template("message.html",title="Не найдено",message="Запрошенная страница или автомобиль не найдены."),404

init_db()
if __name__ == "__main__":
    app.run(debug=True)
