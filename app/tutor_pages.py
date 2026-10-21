from flask import Blueprint, g, render_template
from .auth import login_required, teacher_required

bp = Blueprint("tutor_pages", __name__)


@bp.get("/tutor")
@login_required
def tutor():
    return render_template("tutor.html")


@bp.get("/manage")
@teacher_required
def manage():
    return render_template("manage.html")
