import os
import time
from flask import Flask, render_template, request, jsonify
import requests
import logging

app = Flask(__name__)
app.template_folder = 'templates'
logging.basicConfig(level=logging.INFO)

# تأكد من أن RPC_URL يبدأ بـ https://
RPC_URL = "https://api.devnet.solana.com"  # يمكنك تغييرها إلى الرابط الخاص بك

@app.route('/')
def home():
    user_id = request.headers.get('X-Replit-User-Id', '')
    user_name = request.headers.get('X-Replit-User-Name', '')
    user_roles = request.headers.get('X-Replit-User-Roles', '')

    return render_template(
        'index.html',
        user_id=user_id,
        user_name=user_name,
        user_roles=user_roles,
        RPC_URL=RPC_URL  # تمرير RPC_URL إلى القالب
    )

@app.route('/burn')
def burn():
    return render_template('index.html', RPC_URL=RPC_URL)

@app.route('/batch_process', methods=['POST'])
def batch_process():
    try:
        data = request.get_json()
        accounts = data.get('accounts', [])

        if not accounts:
            return jsonify({"error": "No accounts provided"}), 400

        BATCH_SIZE = 20
        total_accounts = len(accounts)
        processed = 0
        failed = 0

        logging.info(f"Starting batch process for {total_accounts} accounts")

        response = {
            "success": True,
            "total": total_accounts,
            "processed": processed,
            "failed": failed,
            "message": f"Successfully processed {processed} accounts"
        }

        return jsonify(response)
    except Exception as e:
        logging.error(f"Batch process error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/close_accounts', methods=['POST'])
def close_accounts():
    try:
        start_time = time.time()
        wallet = request.form['wallet'].strip()
        
        if not (32 <= len(wallet) <= 44):
            return jsonify({"error": "ERROR: 400 - Invalid address"}), 400

        headers = {"Content-Type": "application/json"}
        logging.info(f"RPC Request for wallet: {wallet[:4]}...{wallet[-4:]}")
        
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed", "commitment": "confirmed"}
            ]
        }

        response = requests.post(RPC_URL, json=data, headers=headers)
        response_time = time.time() - start_time
        logging.info(f"RPC Response received in {response_time:.2f} seconds")

        if response.status_code != 200:
            return jsonify({"error": f"RPC Error: {response.text}"}), 500

        response_json = response.json()
        
        if 'error' in response_json:
            error_message = str(response_json['error'])
            if 'Transaction already processed' in error_message:
                logging.info("Transaction already processed - continuing as success")
                return jsonify({
                    "success": True,
                    "message": "Transaction completed (already processed)",
                    "progress": 100
                })
            else:
                return jsonify({"error": error_message}), 500

        accounts = response_json["result"]["value"]
        logging.info(f"Found {len(accounts)} accounts to process")
        selected_accounts = []

        for acc in accounts:
            try:
                info = acc["account"]["data"]["parsed"]["info"]
                amount = info["tokenAmount"]["uiAmount"]
                if amount > 0:
                    selected_accounts.append({
                        "pubkey": acc["pubkey"],
                        "amount": amount
                    })
            except Exception as e:
                logging.warning(f"Error processing account: {e}")
                continue

        if not selected_accounts:
            return jsonify({"error": "No accounts found to close"}), 400

        return jsonify({
            "success": True,
            "message": f"Found {len(selected_accounts)} accounts to close",
            "accounts": [acc["pubkey"] for acc in selected_accounts],
            "estimated_sol": f"{len(selected_accounts) * 0.002:.3f} SOL"
        })
    except Exception as e:
        logging.error(f"Close accounts error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/check_wallet', methods=['POST'])
def check_wallet():
    try:
        wallet = request.form['wallet'].strip()
        interface = request.form.get('interface', 'cleanup')
        page = int(request.form.get('page', 1))
        per_page = 10

        if not (32 <= len(wallet) <= 44):
            return jsonify({"error": "ERROR: 400 - Invalid address"}), 400

        headers = {"Content-Type": "application/json"}
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ]
        }

        response = requests.post(RPC_URL, json=data, headers=headers)
        response.raise_for_status()

        result = response.json()
        all_accounts = result["result"]["value"]
        total_accounts = len(all_accounts)
        accounts = all_accounts[(page-1)*per_page : page*per_page]

        tokens = []
        for acc in accounts:
            try:
                info = acc["account"]["data"]["parsed"]["info"]
                amount = info["tokenAmount"]["uiAmount"]
                decimals = info["tokenAmount"]["decimals"]

                if interface == 'burn' and amount == 0:
                    continue

                tokens.append({
                    "address": acc["pubkey"],
                    "mint": info["mint"],
                    "amount": amount,
                    "decimals": decimals
                })
            except Exception as e:
                logging.warning(f"Error processing account: {e}")
                continue

        short_wallet = wallet[:4] + "..." + wallet[-4:]

        return jsonify({
            "wallet": short_wallet,
            "tokens": tokens,
            "total_tokens": total_accounts,
            "has_more": len(all_accounts) > page * per_page
        })
    except Exception as e:
        logging.error(f"Wallet check error: {e}")
        return jsonify({"error": "Error connecting to the network"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
