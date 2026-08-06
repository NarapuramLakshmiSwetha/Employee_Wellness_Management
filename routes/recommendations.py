from flask import Blueprint, jsonify, session
import database

recommendations_bp = Blueprint('recommendations', __name__)

@recommendations_bp.route('/api/employee-recommendations')
def employee_recommendations():
    """Return a list of employees with wellness scores and simple recommendations."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    # Fetch all non-admin users
    users = database.get_all_users()
    recs = []
    for u in users:
        if u['job_role'] == 'admin' or u['username'] == 'admin':
            continue
        score = database.calculate_health_score(u['id'])
        if score is None:
            continue
        # Simple recommendation based on score thresholds
        if score >= 80:
            rec = 'Excellent performance – keep up the great habits!'
        elif score >= 60:
            rec = 'Good score – consider minor lifestyle tweaks for further improvement.'
        elif score >= 40:
            rec = 'Average score – focus on key health areas such as exercise and nutrition.'
        else:
            rec = 'Needs improvement – prioritize health check‑ups and adopt healthier habits.'
        recs.append({
            'username': u['username'],
            'full_name': u.get('full_name', ''),
            'wellness_score': score,
            'recommendation': rec
        })
    return jsonify({'success': True, 'employees': recs})
