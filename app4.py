import pdfplumber
import pandas as pd
import re
import matplotlib.pyplot as plt
import streamlit as st

# Global categories dictionary
categories = {
    "Groceries": ["woolworths", "iga", "supermarket", "freshco", "dhesi meat shop", "7eleven", "dollarama"],
    "Dining/Takeout": ["restaurant", "cafe", "tim hortons", "popeyes", "banter ice cream"],
    "Utilities": ["virgin plus", "adobe inc", "internet", "electricity", "water"],
    "Subscriptions": ["canva", "nayax", "netflix", "spotify"],
    "Transportation": ["uber", "lyft", "gas station", "public transit"],
    "Entertainment": ["movie", "concert", "theme park", "music"],
    "Shopping": ["petstock", "clothing", "electronics", "amazon"],
    "Health": ["pharmacy", "hospital", "gym"],
    "Other": []  # Default category
}

# Function to extract lines from PDF
def extract_lines_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        lines = []
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                lines.extend(page_text.splitlines())
    return lines

# Function to detect the statement format
def detect_statement_format(lines):
    # Check for Commonwealth Bank format
    if any("Commonwealth Bank of Australia" in line for line in lines):
        return "commonwealth_bank"
    # Check for credit card format
    elif any("TRANS. POST" in line for line in lines):
        return "credit_card"
    # Check for debit card format
    elif any("OpeningBalance" in line for line in lines):
        return "debit_card"
    # Default to credit card format
    return "credit_card"

# Function to parse transactions for Commonwealth Bank statements
def parse_commonwealth_bank_transactions(lines):
    # Regex pattern for Commonwealth Bank statement format
    pattern = r"(\d{1,2} \w{3})\s+(.*?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$"
    
    transactions = []
    current_transaction = None
    
    for line in lines:
        match = re.match(pattern, line)
        if match:
            # If a new transaction is found, save the previous one (if any)
            if current_transaction:
                transactions.append(current_transaction)
            date, description, debit, credit = match.groups()
            amount = debit if debit else f"-{credit}"  # Use debit or credit as the amount
            current_transaction = (date, description, amount)
        elif current_transaction:
            # If the line doesn't match the pattern, append it to the current transaction's description
            current_transaction = (current_transaction[0], current_transaction[1] + " " + line.strip(), current_transaction[2])
    
    # Add the last transaction
    if current_transaction:
        transactions.append(current_transaction)
    
    return transactions

# Function to parse transactions for credit card statements
def parse_credit_card_transactions(lines):
    # Regex pattern for credit card statement format
    pattern = r"(\d{3})\s+(\w{3} \d{1,2})\s+(\w{3} \d{1,2})\s+(.*?)\s+([\d,]+\.\d{2})$"
    
    transactions = []
    current_transaction = None
    
    for line in lines:
        match = re.match(pattern, line)
        if match:
            # If a new transaction is found, save the previous one (if any)
            if current_transaction:
                transactions.append(current_transaction)
            ref_num, trans_date, post_date, details, amount = match.groups()
            current_transaction = (trans_date, details, amount)
        elif current_transaction:
            # If the line doesn't match the pattern, append it to the current transaction's description
            current_transaction = (current_transaction[0], current_transaction[1] + " " + line.strip(), current_transaction[2])
    
    # Add the last transaction
    if current_transaction:
        transactions.append(current_transaction)
    
    return transactions

# Function to parse transactions for debit card statements
def parse_debit_card_transactions(lines):
    # Regex pattern for debit card statement format
    pattern = r"(\w{3}\d{1,2})\s+(.*?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$"
    
    transactions = []
    current_transaction = None
    
    for line in lines:
        match = re.match(pattern, line)
        if match:
            # If a new transaction is found, save the previous one (if any)
            if current_transaction:
                transactions.append(current_transaction)
            date, transaction_type, amount, balance = match.groups()
            current_transaction = (date, transaction_type, amount)
        elif current_transaction:
            # If the line doesn't match the pattern, append it to the current transaction's description
            current_transaction = (current_transaction[0], current_transaction[1] + " " + line.strip(), current_transaction[2])
    
    # Add the last transaction
    if current_transaction:
        transactions.append(current_transaction)
    
    return transactions

# Function to normalize transactions
def normalize_transactions(transactions, statement_format):
    df = pd.DataFrame(transactions, columns=["Date", "Description", "Amount"])
    df["Amount"] = df["Amount"].str.replace(",", "")
    
    # Convert Amount to numeric, coercing errors to NaN
    df["Amount"] = pd.to_numeric(df["Amount"], errors='coerce')
    
    # Drop rows with NaN values in the Amount column
    df = df.dropna(subset=["Amount"])
    
    # Normalize dates (convert to datetime)
    if statement_format == "commonwealth_bank":
        df["Date"] = pd.to_datetime(df["Date"], format="%d %b", errors="coerce")
    else:
        df["Date"] = pd.to_datetime(df["Date"], format="%b %d", errors="coerce")
    
    # Filter out irrelevant transactions
    if statement_format == "debit_card":
        # Exclude deposits and other non-expense transactions
        df = df[~df["Description"].str.contains("OpeningBalance|ClosingBalance|Deposit|CreditCard/LOCpayment", case=False)]
        # Remove "Pointofsalepurchase" from the description
        df["Description"] = df["Description"].str.replace("Pointofsalepurchase", "", case=False).str.strip()
    elif statement_format == "credit_card":
        # Exclude payment transactions for credit card statements
        df = df[~df["Description"].str.contains("PAYMENT FROM", case=False)]
    elif statement_format == "commonwealth_bank":
        # Exclude non-expense transactions for Commonwealth Bank statements
        df = df[~df["Description"].str.contains("OPENING BALANCE|DEBIT INTEREST", case=False)]
    
    # Truncate descriptions to 3 words
    df["Description"] = df["Description"].apply(lambda x: " ".join(x.split()[:3]))
    
    return df

# Function to categorize expenses
def categorize_expenses(df):
    def get_category(description):
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in description.lower():
                    return category
        return "Other"
    
    df["Category"] = df["Description"].apply(get_category)
    return df

# Streamlit app
def main():
    st.title("Bank Statement Expense Analyzer")
    uploaded_file = st.file_uploader("Upload your bank statement (PDF)", type="pdf")

    if uploaded_file is not None:
        # Extract lines from PDF
        lines = extract_lines_from_pdf(uploaded_file)
        
        # Detect the statement format
        statement_format = detect_statement_format(lines)
        
        # Parse transactions based on the detected format
        if statement_format == "credit_card":
            transactions = parse_credit_card_transactions(lines)
        elif statement_format == "debit_card":
            transactions = parse_debit_card_transactions(lines)
        elif statement_format == "commonwealth_bank":
            transactions = parse_commonwealth_bank_transactions(lines)
        else:
            st.error("Unsupported statement format.")
            return
        
        # Normalize transactions
        df = normalize_transactions(transactions, statement_format)
        
        # Categorize expenses
        df = categorize_expenses(df)
        
        # Allow users to update categories
        st.write("### Update Categories")
        for index, row in df.iterrows():
            new_category = st.selectbox(
                f"Category for: {row['Description']} (Current: {row['Category']})",
                options=list(categories.keys()),
                index=list(categories.keys()).index(row["Category"]),  # Set default value
                key=index
            )
            df.at[index, "Category"] = new_category
        
        # Display transaction data with total
        st.write("### Transaction Data")
        st.write(df)
        
        # Calculate and display total expenses
        total_expenses = df["Amount"].sum()
        st.write(f"### Total Expenses: ${total_expenses:.2f}")
        
        # Analyze expenses
        st.write("### Expense Analysis")
        summary = df.groupby("Category")["Amount"].sum().reset_index()
        
        # Display bar chart
        st.write("#### Bar Chart")
        st.bar_chart(summary.set_index("Category"))
        
        # Display pie chart
        st.write("#### Pie Chart")
        fig, ax = plt.subplots()
        ax.pie(summary["Amount"], labels=summary["Category"], autopct="%1.1f%%", startangle=90)
        ax.axis("equal")  # Equal aspect ratio ensures the pie chart is circular.
        st.pyplot(fig)

# Run the Streamlit app
if __name__ == "__main__":
    main()