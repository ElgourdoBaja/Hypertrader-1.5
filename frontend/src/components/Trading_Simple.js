import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { TrendingUp, TrendingDown, AlertCircle } from 'lucide-react';
import LoadingSpinner from './LoadingSpinner';

const Trading = () => {
  console.log('Trading component loaded'); // Debug log
  const [orderForm, setOrderForm] = useState({
    coin: 'BTC',
    side: 'long',
    orderType: 'limit',
    size: '',
    price: '',
    leverage: 1
  });
  const [marketData, setMarketData] = useState(null);
  const [openOrders, setOpenOrders] = useState([]);
  const [loading, setLoading] = useState(true); // Start with loading true
  const [message, setMessage] = useState(null);

  const coins = ['BTC', 'ETH', 'SOL', 'AVAX', 'MATIC', 'LINK'];

  useEffect(() => {
    console.log('Trading component useEffect triggered');
    fetchTradingData();
  }, [orderForm.coin]);

  const fetchTradingData = async () => {
    console.log('Fetching trading data...');
    try {
      setLoading(true);
      
      // Fetch market data
      console.log(`Fetching market data for ${orderForm.coin}`);
      const marketResponse = await axios.get(`/api/market/${orderForm.coin}`);
      if (marketResponse.data.success) {
        setMarketData(marketResponse.data.data);
        console.log('Market data fetched successfully');
      }

      // Fetch open orders
      console.log('Fetching open orders');
      const ordersResponse = await axios.get('/api/orders/open');
      if (ordersResponse.data.success) {
        setOpenOrders(ordersResponse.data.data);
        console.log(`Open orders fetched: ${ordersResponse.data.data.length} orders`);
      }

    } catch (error) {
      console.error('Error fetching trading data:', error);
      setMessage({ type: 'error', text: 'Failed to fetch trading data' });
    } finally {
      console.log('Setting loading to false');
      setLoading(false);
    }
  };

  const handleInputChange = (field, value) => {
    setOrderForm(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleSubmitOrder = async (e) => {
    e.preventDefault();
    
    if (!orderForm.size || (!orderForm.price && orderForm.orderType === 'limit')) {
      setMessage({ type: 'error', text: 'Please fill in all required fields' });
      return;
    }

    try {
      const orderRequest = {
        coin: orderForm.coin,
        is_buy: orderForm.side === 'long',
        sz: parseFloat(orderForm.size),
        limit_px: orderForm.orderType === 'limit' ? parseFloat(orderForm.price) : null,
        order_type: orderForm.orderType,
        reduce_only: false
      };

      const response = await axios.post('/api/orders', orderRequest);
      
      if (response.data.success) {
        setMessage({ type: 'success', text: 'Order placed successfully!' });
        setOrderForm(prev => ({ ...prev, size: '', price: '' }));
        fetchTradingData(); // Refresh data to show new orders
      } else {
        setMessage({ type: 'error', text: response.data.message || 'Failed to place order' });
      }

    } catch (error) {
      console.error('Error placing order:', error);
      setMessage({ 
        type: 'error', 
        text: error.response?.data?.detail || 'Failed to place order' 
      });
    }
  };

  const handleCancelOrder = async (coin, oid) => {
    try {
      const response = await axios.delete(`/api/orders/${coin}/${oid}`);
      if (response.data.success) {
        setMessage({ type: 'success', text: 'Order cancelled successfully!' });
        fetchTradingData(); // Refresh data to remove cancelled order
      } else {
        setMessage({ type: 'error', text: 'Failed to cancel order' });
      }
    } catch (error) {
      console.error('Error cancelling order:', error);
      setMessage({ type: 'error', text: 'Failed to cancel order' });
    }
  };

  const formatPrice = (price) => {
    return `$${price?.toLocaleString('en-US', { 
      minimumFractionDigits: 2, 
      maximumFractionDigits: 2 
    }) || '0.00'}`;
  };

  // Show initial loading state
  if (loading && !marketData) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold text-white">Trading</h1>
        </div>
        <div className="flex justify-center py-12">
          <LoadingSpinner size="large" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-white">Trading</h1>
        <div className="flex items-center space-x-4">
          {marketData && (
            <>
              <div className="text-right">
                <p className="text-sm text-gray-400">Current Price</p>
                <p className="text-lg font-bold text-white">
                  {formatPrice(marketData.price)}
                </p>
              </div>
              <div className={`px-3 py-1 rounded ${
                marketData.change_24h >= 0 ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
              }`}>
                {marketData.change_24h >= 0 ? '+' : ''}{marketData.change_24h?.toFixed(2)}%
              </div>
            </>
          )}
        </div>
      </div>

      {/* Message Display */}
      {message && (
        <div className={`p-4 rounded-lg flex items-center space-x-2 ${
          message.type === 'success' 
            ? 'bg-green-900 text-green-300 border border-green-700' 
            : 'bg-red-900 text-red-300 border border-red-700'
        }`}>
          <AlertCircle size={20} />
          <span>{message.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Order Form */}
        <div className="bg-gray-800 p-6 rounded-lg border border-gray-700">
          <h2 className="text-xl font-bold text-white mb-4">Place Order</h2>
          
          <form onSubmit={handleSubmitOrder} className="space-y-4">
            {/* Coin Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Asset
              </label>
              <select
                value={orderForm.coin}
                onChange={(e) => handleInputChange('coin', e.target.value)}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:outline-none focus:border-blue-400"
              >
                {coins.map(coin => (
                  <option key={coin} value={coin}>{coin}</option>
                ))}
              </select>
            </div>

            {/* Side Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Side
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => handleInputChange('side', 'long')}
                  className={`py-2 px-4 rounded font-medium transition-colors ${
                    orderForm.side === 'long'
                      ? 'bg-green-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  Long
                </button>
                <button
                  type="button"
                  onClick={() => handleInputChange('side', 'short')}
                  className={`py-2 px-4 rounded font-medium transition-colors ${
                    orderForm.side === 'short'
                      ? 'bg-red-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  Short
                </button>
              </div>
            </div>

            {/* Order Type */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Order Type
              </label>
              <select
                value={orderForm.orderType}
                onChange={(e) => handleInputChange('orderType', e.target.value)}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:outline-none focus:border-blue-400"
              >
                <option value="limit">Limit</option>
                <option value="market">Market</option>
              </select>
            </div>

            {/* Leverage */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Leverage: {orderForm.leverage}x
              </label>
              <input
                type="range"
                min="1"
                max="50"
                value={orderForm.leverage}
                onChange={(e) => handleInputChange('leverage', parseInt(e.target.value))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>1x</span>
                <span>25x</span>
                <span>50x</span>
              </div>
            </div>

            {/* Size */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Size
              </label>
              <input
                type="number"
                step="0.001"
                value={orderForm.size}
                onChange={(e) => handleInputChange('size', e.target.value)}
                placeholder="0.000"
                className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:outline-none focus:border-blue-400"
              />
            </div>

            {/* Price (for limit orders) */}
            {orderForm.orderType === 'limit' && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">
                  Price
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={orderForm.price}
                  onChange={(e) => handleInputChange('price', e.target.value)}
                  placeholder="0.00"
                  className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:outline-none focus:border-blue-400"
                />
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className={`w-full py-3 px-4 rounded font-medium transition-colors ${
                orderForm.side === 'long'
                  ? 'bg-green-600 hover:bg-green-700 text-white'
                  : 'bg-red-600 hover:bg-red-700 text-white'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {loading ? (
                <LoadingSpinner size="small" />
              ) : (
                `${orderForm.side.toUpperCase()} ${orderForm.coin}`
              )}
            </button>
          </form>
        </div>

        {/* Market Information */}
        <div className="bg-gray-800 p-6 rounded-lg border border-gray-700">
          <h2 className="text-xl font-bold text-white mb-4">Market Information</h2>
          
          {loading ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : marketData ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-gray-700 rounded">
                  <p className="text-sm text-gray-400">Current Price</p>
                  <p className="text-lg font-bold text-white">{formatPrice(marketData.price)}</p>
                </div>
                <div className="p-3 bg-gray-700 rounded">
                  <p className="text-sm text-gray-400">24h Change</p>
                  <p className={`text-lg font-bold ${
                    marketData.change_24h >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {marketData.change_24h >= 0 ? '+' : ''}{marketData.change_24h?.toFixed(2)}%
                  </p>
                </div>
                <div className="p-3 bg-gray-700 rounded">
                  <p className="text-sm text-gray-400">Bid Price</p>
                  <p className="text-lg font-bold text-green-400">{formatPrice(marketData.bid)}</p>
                </div>
                <div className="p-3 bg-gray-700 rounded">
                  <p className="text-sm text-gray-400">Ask Price</p>
                  <p className="text-lg font-bold text-red-400">{formatPrice(marketData.ask)}</p>
                </div>
              </div>

              <div className="mt-6">
                <h3 className="text-lg font-semibold text-white mb-3">Popular Pairs</h3>
                <div className="grid grid-cols-2 gap-2">
                  {coins.map(coin => (
                    <button
                      key={coin}
                      onClick={() => handleInputChange('coin', coin)}
                      className={`p-2 rounded text-sm font-medium transition-colors ${
                        orderForm.coin === coin
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                      }`}
                    >
                      {coin}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-gray-400 text-center py-8">No market data available</p>
          )}
        </div>

        {/* Open Orders */}
        <div className="bg-gray-800 p-6 rounded-lg border border-gray-700">
          <h2 className="text-xl font-bold text-white mb-4">Open Orders</h2>
          
          {loading ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : openOrders.length > 0 ? (
            <div className="space-y-3">
              {openOrders.map((order, index) => (
                <div key={index} className="p-3 bg-gray-700 rounded border border-gray-600">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold text-white">{order.coin}</span>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        order.side === 'buy' 
                          ? 'bg-green-900 text-green-300'
                          : 'bg-red-900 text-red-300'
                      }`}>
                        {order.side === 'buy' ? 'LONG' : 'SHORT'}
                      </span>
                    </div>
                    <button
                      onClick={() => handleCancelOrder(order.coin, order.oid)}
                      className="text-red-400 hover:text-red-300 text-sm px-2 py-1 bg-red-900 hover:bg-red-800 rounded transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                  <div className="text-sm text-gray-400">
                    <p>Size: {order.size}</p>
                    {order.price && <p>Price: {formatPrice(order.price)}</p>}
                    <p>Type: {order.order_type}</p>
                    <p>Status: {order.status}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-400">No open orders</p>
              <p className="text-sm text-gray-500 mt-1">Your pending orders will appear here</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Trading;