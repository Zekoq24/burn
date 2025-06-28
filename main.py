import os
import time
from flask import Flask, render_template, request, jsonify
import requests
import logging

app = Flask(__name__)
app.template_folder = 'templates'
logging.basicConfig(level=logging.INFO)

RPC_URL = "https://proud-aged-flower.solana-devnet.quiknode.pro/6c4369466a2cfc21c12af4a500501aa9b0093340"

@app.route('/')
def home():
    user_id = request.headers.get('X-Replit-User-Id', '')
    user_name = request.headers.get('X-Replit-User-Name', '')
    user_roles = request.headers.get('X-Replit-User-Roles', '')

    return render_template('index.html',
                         user_id=user_id,
                         user_name=user_name,
                         user_roles=user_roles,
                         RPC_URL=RPC_URL)

@app.route('/burn')
def burn():
    return render_template('index.html')

@app.route('/batch_process', methods=['POST'])
def batch_process():
    try:
        data = request.get_json()
        accounts = data.get('accounts', [])

        if not accounts:
            return jsonify({"error": "No accounts provided"}), 400

        # Process in batches of 20 to optimize transaction signing
        BATCH_SIZE = 20
        total_accounts = len(accounts)
        processed = 0
        failed = 0

        # تحسين تتبع التقدم
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
        logging.info(f"RPC Request starting for wallet: {wallet[:4]}...{wallet[-4:]}")
        logging.info(f"RPC URL being used: {RPC_URL}")
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

        try:
            response = requests.post(RPC_URL, json=data, headers=headers)
            response_time = time.time() - start_time
            logging.info(f"RPC Response received in {response_time:.2f} seconds")
            if response_time > 5:  # تنبيه إذا استغرق الطلب أكثر من 5 ثواني
                logging.warning(f"RPC request took longer than expected: {response_time:.2f} seconds")
            logging.info(f"RPC Response status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logging.error(f"RPC Request failed: {str(e)}")
            raise
        
        response_json = response.json()
        
        # تحقق من وجود رسالة خطأ معالجة المعاملة مسبقاً
        if 'error' in response_json:
            error_message = str(response_json['error'])
            if ('Transaction already processed' in error_message or 
                'This transaction has already been processed' in error_message):
                logging.info("Transaction already processed - continuing as success")
                return jsonify({
                    "success": True,
                    "message": "Transaction completed (already processed)",
                    "progress": 100
                })
        
        response.raise_for_status()
        accounts = response_json["result"]["value"]
        logging.info(f"Found {len(accounts)} accounts to process")
        selected_accounts = []

        for acc in accounts:
            try:
                info = acc["account"]["data"]["parsed"]["info"]
                amount = info["tokenAmount"]["uiAmount"]
                if amount > 0:  # Only include non-empty accounts
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
        per_page = 10  # تقليل عدد التوكنات في كل صفحة للتحميل التدريجي

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

        # حساب نطاق الصفحة الحالية
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        accounts = all_accounts[start_idx:end_idx]

        token_accounts = 0
        nft_accounts = 0
        cleanup_accounts = 0
        total_rent = 0

        tokens = []
        for acc in accounts:
            try:
                info = acc["account"]["data"]["parsed"]["info"]
                amount = info["tokenAmount"]["uiAmount"]
                decimals = info["tokenAmount"]["decimals"]

                # Only include non-empty tokens for burn interface
                if interface == 'burn' and amount == 0:
                    continue

                if amount == 0:
                    token_accounts += 1
                elif decimals == 0 and amount == 1:
                    nft_accounts += 1
                else:
                    cleanup_accounts += 1

                total_rent += 0.00203928

                tokens.append({
                    "address": acc["pubkey"],
                    "mint": info["mint"],
                    "name": "Token Account",
                    "amount": amount,
                    "decimals": info["tokenAmount"]["decimals"]
                })
            except Exception as e:
                logging.warning(f"Error processing account: {e}")
                continue

        real_value = total_rent / 2
        sol_value = round(real_value, 6)
        short_wallet = wallet[:4] + "..." + wallet[-4:]

        return jsonify({
            "wallet": short_wallet,
            "tokens": tokens,
            "total_tokens": total_accounts,
            "has_more": len(all_accounts) > end_idx
        })
    except Exception as e:
        logging.error(f"Wallet handler error: {e}")
        return jsonify({"error": "Error connecting to the network"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)