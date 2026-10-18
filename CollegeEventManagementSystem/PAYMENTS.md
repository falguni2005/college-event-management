# Real UPI payment integration checklist

This project includes the payment data model and payment screen, but does not collect real money until a gateway is configured and its server-side verification is implemented.

1. Choose a payment gateway that supports the merchant account and UPI checkout/QR flow you need.
2. Create an order on the Flask server using the event fee and registration ID.
3. Send the order ID and public checkout details to the client. Never expose the secret key.
4. For mobile, use the gateway's supported checkout/UPI intent flow; supported apps vary by device.
5. For laptop, render the gateway-generated, order-specific QR code and let the student scan it with a UPI app.
6. Verify the payment signature and/or webhook on the server. Verify amount, currency, order ID, and final payment status.
7. Mark the registration paid only after verification; make webhook handling idempotent.
8. Provide clear cancellation/refund handling and never store UPI PINs.

The included `/payment/<id>` page deliberately displays a setup notice rather than falsely claiming a payment succeeded. Configure and test gateway integration in test mode before any production use.
