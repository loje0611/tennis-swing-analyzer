import streamlit as st


def styles():
    st.markdown("""
        <style>
        /* Global Font Adjustments */
        html, body, [class*="css"] {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }
        
        /* Metric Styling */
        div[data-testid="stMetricValue"] {
            font-size: 3rem !important;
            font-weight: 700;
        }
        
        /* Big Swing Card */
        .swing-card {
            border-radius: 20px;
            padding: 40px 20px;
            text-align: center;
            margin-bottom: 20px;
            color: white;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }
        .swing-fh { 
            background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%); 
            border: 4px solid #1e7e34; 
        }
        .swing-bh { 
            background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); 
            border: 4px solid #0056b3; 
        }
        .swing-ready { 
            background: linear-gradient(135deg, #343a40 0%, #23272b 100%); 
            border: 4px solid #23272b; 
        }
        
        .swing-title { font-size: 2rem; opacity: 0.9; margin: 0; font-weight: 500; letter-spacing: 1px; }
        .swing-label { font-size: 6rem; font-weight: 900; margin: 10px 0; line-height: 1.0; text-transform: uppercase; }
        .swing-speed { font-size: 2.5rem; font-weight: 700; background: rgba(0,0,0,0.2); padding: 5px 20px; border-radius: 10px; display: inline-block; margin-top: 15px; }

        /* Status Text Colors */
        .swing-label-ready { color: #888888; }
        .swing-label-fh { color: #00CC66; }
        .swing-label-bh { color: #3366FF; }

        /* Recent Shots Badges */
        .shot-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 1rem;
            margin: 4px;
            color: white;
        }
        .shot-badge-fh { background: linear-gradient(135deg, #28a745, #1e7e34); }
        .shot-badge-bh { background: linear-gradient(135deg, #007bff, #0056b3); }

        /* Tabs Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 60px;
            white-space: pre-wrap;
            background-color: #1e1e1e;
            border-radius: 10px;
            color: white;
            font-size: 1.2rem;
            width: 100%;
            justify-content: center;
        }
        .stTabs [aria-selected="true"] {
            background-color: #ff4b4b !important;
            color: white !important;
        }
        
        /* Sidebar — theme-aware */
        @media (prefers-color-scheme: light) {
            section[data-testid="stSidebar"] {
                background-color: #f5f5f5;
                color: #222;
            }
            section[data-testid="stSidebar"] h1,
            section[data-testid="stSidebar"] h2,
            section[data-testid="stSidebar"] h3,
            section[data-testid="stSidebar"] p,
            section[data-testid="stSidebar"] span,
            section[data-testid="stSidebar"] label {
                color: #222 !important;
            }
        }
        @media (prefers-color-scheme: dark) {
            section[data-testid="stSidebar"] {
                background-color: #111;
                color: #eee;
            }
        }
        
        </style>
    """, unsafe_allow_html=True)
